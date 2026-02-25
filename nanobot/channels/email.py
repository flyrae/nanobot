"""Email channel implementation using IMAP polling + SMTP replies."""

import asyncio
import base64
import html
import imaplib
import io
import mimetypes
import re
import smtplib
import ssl
from datetime import date
from email import policy
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import EmailConfig


class EmailChannel(BaseChannel):
    """
    Email channel.

    Inbound:
    - Poll IMAP mailbox for unread messages.
    - Convert each message into an inbound event.

    Outbound:
    - Send responses via SMTP back to the sender address.
    """

    name = "email"
    _IMAP_MONTHS = (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    )

    def __init__(self, config: EmailConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: EmailConfig = config
        self._last_subject_by_chat: dict[str, str] = {}
        self._last_message_id_by_chat: dict[str, str] = {}
        self._processed_uids: set[str] = set()  # Capped to prevent unbounded growth
        self._MAX_PROCESSED_UIDS = 100000

    async def start(self) -> None:
        """Start polling IMAP for inbound emails."""
        if not self.config.consent_granted:
            logger.warning(
                "Email channel disabled: consent_granted is false. "
                "Set channels.email.consentGranted=true after explicit user permission."
            )
            return

        if not self._validate_config():
            return

        self._running = True
        logger.info("Starting Email channel (IMAP polling mode)...")

        poll_seconds = max(5, int(self.config.poll_interval_seconds))
        while self._running:
            try:
                inbound_items = await asyncio.to_thread(self._fetch_new_messages)
                for item in inbound_items:
                    sender = item["sender"]
                    subject = item.get("subject", "")
                    message_id = item.get("message_id", "")

                    if subject:
                        self._last_subject_by_chat[sender] = subject
                    if message_id:
                        self._last_message_id_by_chat[sender] = message_id

                    await self._handle_message(
                        sender_id=sender,
                        chat_id=sender,
                        content=item["content"],
                        metadata=item.get("metadata", {}),
                    )
            except Exception as e:
                logger.error("Email polling error: {}", e)

            await asyncio.sleep(poll_seconds)

    async def stop(self) -> None:
        """Stop polling loop."""
        self._running = False

    async def send(self, msg: OutboundMessage) -> None:
        """Send email via SMTP, with optional media attachments."""
        if not self.config.consent_granted:
            logger.warning("Skip email send: consent_granted is false")
            return

        # Skip streaming/intermediate media pushes — email should only send
        # the final consolidated reply, not one email per screenshot step.
        if (msg.metadata or {}).get("streaming_media"):
            logger.debug("Email channel: skipping streaming media push (will attach in final reply)")
            return

        force_send = bool((msg.metadata or {}).get("force_send"))
        if not self.config.auto_reply_enabled and not force_send:
            logger.info("Skip automatic email reply: auto_reply_enabled is false")
            return

        if not self.config.smtp_host:
            logger.warning("Email channel SMTP host not configured")
            return

        to_addr = msg.chat_id.strip()
        if not to_addr:
            logger.warning("Email channel missing recipient address")
            return

        # Determine if this is a reply (recipient has sent us an email before)
        is_reply = to_addr in self._last_subject_by_chat
        force_send = bool((msg.metadata or {}).get("force_send"))

        # autoReplyEnabled only controls automatic replies, not proactive sends
        if is_reply and not self.config.auto_reply_enabled and not force_send:
            logger.info("Skip automatic email reply to {}: auto_reply_enabled is false", to_addr)
            return

        base_subject = self._last_subject_by_chat.get(to_addr, "nanobot reply")
        subject = self._reply_subject(base_subject)
        if msg.metadata and isinstance(msg.metadata.get("subject"), str):
            override = msg.metadata["subject"].strip()
            if override:
                subject = override

        email_msg = EmailMessage()
        email_msg["From"] = self.config.from_address or self.config.smtp_username or self.config.imap_username
        email_msg["To"] = to_addr
        email_msg["Subject"] = subject

        # Attach media files (images inline, others as attachments)
        media_files = self._resolve_media(msg.media)
        if media_files:
            self._build_rich_email(email_msg, msg.content or "", media_files)
        else:
            email_msg.set_content(msg.content or "")

        in_reply_to = self._last_message_id_by_chat.get(to_addr)
        if in_reply_to:
            email_msg["In-Reply-To"] = in_reply_to
            email_msg["References"] = in_reply_to

        try:
            await asyncio.to_thread(self._smtp_send, email_msg)
            if media_files:
                logger.info(f"Sent email to {to_addr} with {len(media_files)} attachment(s)")
        except Exception as e:
            logger.error("Error sending email to {}: {}", to_addr, e)
            raise

    def _validate_config(self) -> bool:
        missing = []
        if not self.config.imap_host:
            missing.append("imap_host")
        if not self.config.imap_username:
            missing.append("imap_username")
        if not self.config.imap_password:
            missing.append("imap_password")
        if not self.config.smtp_host:
            missing.append("smtp_host")
        if not self.config.smtp_username:
            missing.append("smtp_username")
        if not self.config.smtp_password:
            missing.append("smtp_password")

        if missing:
            logger.error("Email channel not configured, missing: {}", ', '.join(missing))
            return False
        return True

    def _make_ssl_context(self) -> ssl.SSLContext:
        """Create an SSL context, optionally skipping certificate verification."""
        ctx = ssl.create_default_context()
        if not self.config.ssl_verify:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _smtp_send(self, msg: EmailMessage) -> None:
        timeout = 30
        if self.config.smtp_use_ssl:
            with smtplib.SMTP_SSL(
                self.config.smtp_host,
                self.config.smtp_port,
                timeout=timeout,
                context=self._make_ssl_context(),
            ) as smtp:
                smtp.login(self.config.smtp_username, self.config.smtp_password)
                smtp.send_message(msg)
            return

        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=timeout) as smtp:
            if self.config.smtp_use_tls:
                smtp.starttls(context=self._make_ssl_context())
            smtp.login(self.config.smtp_username, self.config.smtp_password)
            smtp.send_message(msg)

    def _fetch_new_messages(self) -> list[dict[str, Any]]:
        """Poll IMAP and return parsed unread messages."""
        return self._fetch_messages(
            search_criteria=("UNSEEN",),
            mark_seen=self.config.mark_seen,
            dedupe=True,
            limit=0,
        )

    def fetch_messages_between_dates(
        self,
        start_date: date,
        end_date: date,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Fetch messages in [start_date, end_date) by IMAP date search.

        This is used for historical summarization tasks (e.g. "yesterday").
        """
        if end_date <= start_date:
            return []

        return self._fetch_messages(
            search_criteria=(
                "SINCE",
                self._format_imap_date(start_date),
                "BEFORE",
                self._format_imap_date(end_date),
            ),
            mark_seen=False,
            dedupe=False,
            limit=max(1, int(limit)),
        )

    def _fetch_messages(
        self,
        search_criteria: tuple[str, ...],
        mark_seen: bool,
        dedupe: bool,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fetch messages by arbitrary IMAP search criteria."""
        messages: list[dict[str, Any]] = []
        mailbox = self.config.imap_mailbox or "INBOX"

        if self.config.imap_use_ssl:
            client = imaplib.IMAP4_SSL(
                self.config.imap_host,
                self.config.imap_port,
                ssl_context=self._make_ssl_context(),
            )
        else:
            client = imaplib.IMAP4(self.config.imap_host, self.config.imap_port)

        try:
            client.login(self.config.imap_username, self.config.imap_password)
            logger.debug(f"IMAP login OK for {self.config.imap_username}")
            status, select_data = client.select(mailbox)
            if status != "OK":
                detail = select_data[0].decode(errors='replace') if select_data and select_data[0] else 'unknown'
                logger.error(
                    f"IMAP SELECT '{mailbox}' failed: status={status}, "
                    f"detail={detail}. "
                    f"Check that IMAP is enabled in your mailbox settings "
                    f"and the authorization code is valid."
                )
                return messages
            logger.debug(f"IMAP SELECT '{mailbox}' OK")

            status, data = client.search(None, *search_criteria)
            if status != "OK" or not data:
                logger.debug(f"IMAP SEARCH returned status={status}, no results")
                return messages

            ids = data[0].split()
            if limit > 0 and len(ids) > limit:
                ids = ids[-limit:]
            for imap_id in ids:
                status, fetched = client.fetch(imap_id, "(BODY.PEEK[] UID)")
                if status != "OK" or not fetched:
                    continue

                raw_bytes = self._extract_message_bytes(fetched)
                if raw_bytes is None:
                    continue

                uid = self._extract_uid(fetched)
                if dedupe and uid and uid in self._processed_uids:
                    continue

                parsed = BytesParser(policy=policy.default).parsebytes(raw_bytes)
                sender = parseaddr(parsed.get("From", ""))[1].strip().lower()
                if not sender:
                    continue

                subject = self._decode_header_value(parsed.get("Subject", ""))
                date_value = parsed.get("Date", "")
                message_id = parsed.get("Message-ID", "").strip()
                body = self._extract_text_body(parsed)

                if not body:
                    body = "(empty email body)"

                body = body[: self.config.max_body_chars]
                content = (
                    f"Email received.\n"
                    f"From: {sender}\n"
                    f"Subject: {subject}\n"
                    f"Date: {date_value}\n\n"
                    f"{body}"
                )

                metadata = {
                    "message_id": message_id,
                    "subject": subject,
                    "date": date_value,
                    "sender_email": sender,
                    "uid": uid,
                }
                messages.append(
                    {
                        "sender": sender,
                        "subject": subject,
                        "message_id": message_id,
                        "content": content,
                        "metadata": metadata,
                    }
                )

                if dedupe and uid:
                    self._processed_uids.add(uid)
                    # mark_seen is the primary dedup; this set is a safety net
                    if len(self._processed_uids) > self._MAX_PROCESSED_UIDS:
                        # Evict a random half to cap memory; mark_seen is the primary dedup
                        self._processed_uids = set(list(self._processed_uids)[len(self._processed_uids) // 2:])

                if mark_seen:
                    client.store(imap_id, "+FLAGS", "\\Seen")
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP error for {self.config.imap_host}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching emails: {e}")
        finally:
            try:
                client.logout()
            except Exception:
                pass

        if messages:
            logger.info(f"Fetched {len(messages)} email(s) from {mailbox}")
        else:
            logger.debug(f"No new emails from {mailbox}")
        return messages

    @classmethod
    def _format_imap_date(cls, value: date) -> str:
        """Format date for IMAP search (always English month abbreviations)."""
        month = cls._IMAP_MONTHS[value.month - 1]
        return f"{value.day:02d}-{month}-{value.year}"

    @staticmethod
    def _extract_message_bytes(fetched: list[Any]) -> bytes | None:
        for item in fetched:
            if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (bytes, bytearray)):
                return bytes(item[1])
        return None

    @staticmethod
    def _extract_uid(fetched: list[Any]) -> str:
        for item in fetched:
            if isinstance(item, tuple) and item and isinstance(item[0], (bytes, bytearray)):
                head = bytes(item[0]).decode("utf-8", errors="ignore")
                m = re.search(r"UID\s+(\d+)", head)
                if m:
                    return m.group(1)
        return ""

    @staticmethod
    def _decode_header_value(value: str) -> str:
        if not value:
            return ""
        try:
            return str(make_header(decode_header(value)))
        except Exception:
            return value

    @classmethod
    def _extract_text_body(cls, msg: Any) -> str:
        """Best-effort extraction of readable body text."""
        if msg.is_multipart():
            plain_parts: list[str] = []
            html_parts: list[str] = []
            for part in msg.walk():
                if part.get_content_disposition() == "attachment":
                    continue
                content_type = part.get_content_type()
                try:
                    payload = part.get_content()
                except Exception:
                    payload_bytes = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset() or "utf-8"
                    payload = payload_bytes.decode(charset, errors="replace")
                if not isinstance(payload, str):
                    continue
                if content_type == "text/plain":
                    plain_parts.append(payload)
                elif content_type == "text/html":
                    html_parts.append(payload)
            if plain_parts:
                return "\n\n".join(plain_parts).strip()
            if html_parts:
                return cls._html_to_text("\n\n".join(html_parts)).strip()
            return ""

        try:
            payload = msg.get_content()
        except Exception:
            payload_bytes = msg.get_payload(decode=True) or b""
            charset = msg.get_content_charset() or "utf-8"
            payload = payload_bytes.decode(charset, errors="replace")
        if not isinstance(payload, str):
            return ""
        if msg.get_content_type() == "text/html":
            return cls._html_to_text(payload).strip()
        return payload.strip()

    @staticmethod
    def _html_to_text(raw_html: str) -> str:
        text = re.sub(r"<\s*br\s*/?>", "\n", raw_html, flags=re.IGNORECASE)
        text = re.sub(r"<\s*/\s*p\s*>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        return html.unescape(text)

    def _reply_subject(self, base_subject: str) -> str:
        subject = (base_subject or "").strip() or "nanobot reply"
        prefix = self.config.subject_prefix or "Re: "
        if subject.lower().startswith("re:"):
            return subject
        return f"{prefix}{subject}"

    # ---- Media / attachment helpers ----

    def _resolve_media(self, media: list[str] | None) -> list[tuple[Path, str, bytes]]:
        """Resolve media paths to (path, mime_type, data) tuples.

        Skips files that don't exist or exceed the size limit.
        Compresses oversized images when Pillow is available.
        Returns a list ready for attachment.
        """
        if not media:
            return []

        results: list[tuple[Path, str, bytes]] = []
        for item in media:
            # Skip data-URLs (not applicable for email attachments)
            if item.startswith("data:"):
                decoded = self._decode_data_url(item)
                if decoded:
                    mime, raw = decoded
                    ext = mimetypes.guess_extension(mime) or ".bin"
                    pseudo_path = Path(f"attachment{ext}")
                    results.append((pseudo_path, mime, raw))
                continue

            path = Path(item)
            if not path.exists() or not path.is_file():
                logger.warning(f"Email media: skipping non-existent file {path}")
                continue

            mime, _ = mimetypes.guess_type(path.name)
            if not mime:
                mime = "application/octet-stream"

            file_bytes = path.read_bytes()
            if len(file_bytes) > self.config.media_max_bytes:
                # Try compressing if it's an image
                compressed = self._compress_image(path, self.config.media_max_bytes)
                if compressed:
                    results.append((path, compressed[0], compressed[1]))
                    logger.info(
                        f"Email media: compressed {path.name} "
                        f"({len(file_bytes)} -> {len(compressed[1])} bytes)"
                    )
                else:
                    logger.warning(
                        f"Email media: skipping oversized file {path.name} "
                        f"({len(file_bytes)} > {self.config.media_max_bytes})"
                    )
                continue

            results.append((path, mime, file_bytes))
            logger.debug(f"Email media: attached {path.name} ({mime}, {len(file_bytes)} bytes)")

        return results

    @staticmethod
    def _decode_data_url(data_url: str) -> tuple[str, bytes] | None:
        """Decode a data:mime;base64,... URL into (mime, raw_bytes)."""
        try:
            header, b64data = data_url.split(",", 1)
            mime = header.split(":")[1].split(";")[0]
            return (mime, base64.b64decode(b64data))
        except Exception:
            return None

    def _build_rich_email(
        self,
        email_msg: EmailMessage,
        text_body: str,
        media_files: list[tuple[Path, str, bytes]],
    ) -> None:
        """Build a multipart email with inline images and file attachments.

        Images (image/*) are embedded inline in an HTML body so they render
        directly in the recipient's mail client.  Non-image files are added
        as standard attachments.
        """
        inline_images: list[tuple[str, str, bytes]] = []  # (cid, mime, data)
        attachments: list[tuple[Path, str, bytes]] = []

        for path, mime, data in media_files:
            if mime.startswith("image/"):
                cid = f"img{len(inline_images)}@nanobot"
                inline_images.append((cid, mime, data))
            else:
                attachments.append((path, mime, data))

        # Build HTML body with inline images
        escaped_text = html.escape(text_body).replace("\n", "<br>\n")
        html_parts = [
            "<html><body>",
            f"<div style=\"font-family:sans-serif;white-space:pre-wrap\">{escaped_text}</div>",
        ]
        if inline_images:
            html_parts.append("<br>")
            for cid, _, _ in inline_images:
                html_parts.append(
                    f'<div><img src="cid:{cid}" style="max-width:100%;height:auto"></div><br>'
                )
        html_parts.append("</body></html>")
        html_body = "\n".join(html_parts)

        # Set plain-text as primary, HTML as alternative
        email_msg.set_content(text_body)
        email_msg.add_alternative(html_body, subtype="html")

        # Embed inline images into the HTML part
        if inline_images:
            html_part = email_msg.get_payload()[-1]  # the text/html alternative
            for cid, mime, data in inline_images:
                maintype, subtype = mime.split("/", 1)
                html_part.add_related(
                    data,
                    maintype=maintype,
                    subtype=subtype,
                    cid=f"<{cid}>",
                )

        # Add non-image files as regular attachments
        for path, mime, data in attachments:
            maintype, subtype = mime.split("/", 1)
            email_msg.add_attachment(
                data,
                maintype=maintype,
                subtype=subtype,
                filename=path.name,
            )

    @staticmethod
    def _compress_image(
        path: Path,
        max_bytes: int,
        *,
        min_quality: int = 30,
        max_dimension: int = 1920,
    ) -> tuple[str, bytes] | None:
        """Compress an image to fit within *max_bytes*.

        Returns ``(mime, raw_bytes)`` on success, or ``None``.
        """
        try:
            from PIL import Image
        except ImportError:
            logger.debug("_compress_image: Pillow not installed, cannot compress")
            return None

        try:
            img = Image.open(path)
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")

            w, h = img.size
            if max(w, h) > max_dimension:
                ratio = max_dimension / max(w, h)
                img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

            for quality in range(85, min_quality - 1, -5):
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=quality, optimize=True)
                if buf.tell() <= max_bytes:
                    return ("image/jpeg", buf.getvalue())

            return None
        except Exception as exc:
            logger.warning(f"_compress_image: error processing {path}: {exc}")
            return None
