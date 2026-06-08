# =========================
# services/media_service.py
# Manejo de media, watermark y envío agrupado
# =========================

import logging
import os
import time
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont
from telegram import InputMediaPhoto, InputMediaVideo, Update
from telegram.ext import Application

from config import (
    ENABLE_WATERMARK_PHOTOS,
    MAX_MEDIA_PER_BUCKET,
    WM_DIR,
    WM_FONT_SIZE,
    now_peru_str,
)
from utils.telegram_utils import tg_call_with_retry

logger = logging.getLogger("media_service")


# =========================
# EXTRACT MEDIA
# =========================
def extract_media_from_message(update: Update) -> Optional[Dict[str, str]]:
    msg = update.message
    if not msg:
        return None

    if msg.photo:
        return {"type": "photo", "file_id": msg.photo[-1].file_id}

    if msg.video:
        return {"type": "video", "file_id": msg.video.file_id}

    if msg.document and (msg.document.mime_type or "").startswith("video/"):
        return {"type": "video", "file_id": msg.document.file_id}

    return None


# =========================
# WATERMARK
# =========================
def _fmt_latlon(lat: Optional[float], lon: Optional[float]) -> str:
    if lat is None or lon is None:
        return "Lat/Lon: N/D"
    return f"Lat/Lon: {lat:.6f}, {lon:.6f}"


def _try_load_font(size: int):
    for font_name in ("arial.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(font_name, size)
        except Exception:
            continue
    return ImageFont.load_default()


async def apply_watermark_photo_if_needed(
    app: Application,
    file_id: str,
    lat: Optional[float],
    lon: Optional[float],
    sent_dt_local: str,
) -> Tuple[str, Optional[str]]:
    if not ENABLE_WATERMARK_PHOTOS:
        return file_id, None

    try:
        os.makedirs(WM_DIR, exist_ok=True)

        tg_file = await tg_call_with_retry(lambda: app.bot.get_file(file_id), what="get_file")
        local_in = os.path.join(WM_DIR, f"in_{int(time.time() * 1000)}.jpg")
        local_out = os.path.join(WM_DIR, f"wm_{int(time.time() * 1000)}.jpg")

        await tg_call_with_retry(
            lambda: tg_file.download_to_drive(custom_path=local_in),
            what="download_to_drive",
        )

        im = Image.open(local_in).convert("RGB")
        draw = ImageDraw.Draw(im)
        font = _try_load_font(WM_FONT_SIZE)

        text = f"{sent_dt_local} | {_fmt_latlon(lat, lon)}"

        padding = 10
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except Exception:
            tw = int(draw.textlength(text, font=font))
            th = WM_FONT_SIZE + 6

        x = 10
        y = im.height - th - padding * 2 - 10
        rect = [x - 5, y - 5, x + tw + padding, y + th + padding]

        draw.rectangle(rect, fill=(0, 0, 0))
        draw.text((x + 5, y + 5), text, font=font, fill=(255, 255, 255))

        im.save(local_out, "JPEG", quality=90)

        try:
            os.remove(local_in)
        except Exception:
            pass

        return file_id, local_out

    except Exception as e:
        logger.warning("No se pudo aplicar watermark: %s", e)
        return file_id, None


def cleanup_wm_dir_if_empty() -> None:
    try:
        if os.path.isdir(WM_DIR) and not os.listdir(WM_DIR):
            os.rmdir(WM_DIR)
    except Exception:
        pass


def cleanup_session_temp_files(s_: Dict) -> None:
    try:
        for section in ("fachada",):
            for item in s_.get(section, {}).get("media", []):
                p = item.get("wm_file")
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

        for sec in ("cableado", "cuadrilla"):
            for _, data in s_.get(sec, {}).items():
                for item in data.get("media", []):
                    p = item.get("wm_file")
                    if p and os.path.exists(p):
                        try:
                            os.remove(p)
                        except Exception:
                            pass

        for item in s_.get("opcionales", {}).get("media", []):
            p = item.get("wm_file")
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

        info_sup = s_.get("info_supervision", {})
        rec = info_sup.get("recorrido_media")
        if isinstance(rec, dict):
            p = rec.get("wm_file")
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
    finally:
        cleanup_wm_dir_if_empty()


# =========================
# SEND MEDIA
# =========================
def to_input_media(item: Dict[str, str]):
    if item["type"] == "photo":
        return InputMediaPhoto(item["file_id"])
    return InputMediaVideo(item["file_id"])


async def send_media_section(app: Application, chat_id: int, title: str, media_items: List[Dict[str, str]]):
    if not media_items:
        return

    await tg_call_with_retry(
        lambda: app.bot.send_message(chat_id=chat_id, text=title),
        what="send_media_title",
    )

    batch: List[Dict[str, str]] = []

    for it in media_items:
        if it.get("type") == "photo" and it.get("wm_file") and os.path.exists(it["wm_file"]):
            if batch:
                for i in range(0, len(batch), 10):
                    chunk = batch[i:i + 10]
                    media = [to_input_media(x) for x in chunk]
                    await tg_call_with_retry(
                        lambda m=media: app.bot.send_media_group(chat_id=chat_id, media=m),
                        what="send_media_group_flush",
                    )
                batch = []

            with open(it["wm_file"], "rb") as f:
                await tg_call_with_retry(
                    lambda fh=f: app.bot.send_photo(chat_id=chat_id, photo=fh),
                    what="send_photo_wm",
                )
        else:
            batch.append(it)

    if batch:
        for i in range(0, len(batch), 10):
            chunk = batch[i:i + 10]
            media = [to_input_media(x) for x in chunk]
            await tg_call_with_retry(
                lambda m=media: app.bot.send_media_group(chat_id=chat_id, media=m),
                what="send_media_group",
            )


# =========================
# BUCKET HELPERS
# =========================
def ensure_bucket(s: Dict, section: str, bucket: Optional[str]) -> Dict:
    if section == "fachada":
        return s["fachada"]
    if section == "opcionales":
        return s["opcionales"]
    if section in ("cableado", "cuadrilla"):
        if not bucket:
            raise ValueError("bucket requerido")
        if bucket not in s[section]:
            s[section][bucket] = {"media": [], "obs": ""}
        return s[section][bucket]
    raise ValueError("section inválida")


def can_add_more_media(bucket_data: Dict) -> bool:
    return len(bucket_data.get("media", [])) < MAX_MEDIA_PER_BUCKET


def build_saved_count_text(bucket_data: Dict) -> str:
    cnt = len(bucket_data.get("media", []))
    return f"✅ Guardado ({cnt}/{MAX_MEDIA_PER_BUCKET})."