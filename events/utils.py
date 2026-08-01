import io
import qrcode
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader


def generate_ticket_pdf(ticket):
    # Создаем буфер в оперативной памяти (чтобы не сохранять файл на жесткий диск)
    buffer = io.BytesIO()

    # Создаем холст PDF размером А4
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # --- 1. Генерируем QR-код ---
    qr = qrcode.QRCode(version=1, box_size=10, border=1)
    qr.add_data(str(ticket.code))  # Вшиваем тот самый UUID билета!
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    # Сохраняем картинку QR-кода тоже в память
    img_buffer = io.BytesIO()
    img.save(img_buffer, format="PNG")
    img_buffer.seek(0)

    # --- 2. Рисуем текст в PDF ---
    # ВНИМАНИЕ: Замени ticket.event.title на правильный путь, если у тебя связь идет через Order
    event_title = ticket.order.event.title if hasattr(ticket, 'order') else "Event Ticket"

    p.setFont("Helvetica-Bold", 24)
    p.drawString(2 * cm, height - 3 * cm, "E-BILET STORE")

    p.setFont("Helvetica", 16)
    p.drawString(2 * cm, height - 4.5 * cm, f"Event: {event_title}")
    p.drawString(2 * cm, height - 5.5 * cm, f"Ticket ID: {str(ticket.id)}")

    # --- 3. Вставляем QR-код в PDF ---
    # Размещаем его справа вверху
    p.drawImage(ImageReader(img_buffer), width - 7 * cm, height - 7 * cm, width=5 * cm, height=5 * cm)

    # Добавляем красивую линию отрыва
    p.setDash(6, 3)
    p.line(0, height - 8 * cm, width, height - 8 * cm)

    # Завершаем создание страницы и сохраняем
    p.showPage()
    p.save()

    # Возвращаем курсор буфера в начало, чтобы Django мог его прочитать
    buffer.seek(0)
    return buffer