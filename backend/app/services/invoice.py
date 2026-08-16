"""PDF invoice generation for booking charges.

One invoice per `BookingCharge`, generated on demand when a charge email is
sent (see app.services.booking_emails) rather than stored — the charge
itself (amount, currency, Stripe PaymentIntent id) is the durable record;
the PDF is just a formatted view of it for the guest's inbox.

Issued in the guest's preferred_language, resolved the same way
app.services.email_templates resolves the surrounding email (falling back
to the default language when unset/unsupported). Labels live in
data/<language>/invoice.json rather than in this module, matching how
email wording lives in data/ rather than Python.
"""

import json
from functools import lru_cache

from fpdf import FPDF

from app.core.config import settings
from app.core.money import format_money
from app.models.booking import Booking, BookingCharge
from app.models.guest import Guest, Language
from app.services.email_templates import DATA_DIR, resolve_language


@lru_cache(maxsize=None)
def _invoice_labels(language: Language) -> dict:
    raw = (DATA_DIR / language / "invoice.json").read_text(encoding="utf-8")
    return json.loads(raw)


def invoice_number_for(charge: BookingCharge) -> str:
    return f"INV-{charge.stripe_payment_intent_id}"


def build_charge_invoice_pdf(*, booking: Booking, guest: Guest, charge: BookingCharge) -> bytes:
    labels = _invoice_labels(resolve_language(guest.preferred_language))
    charge_description = labels["charge_reasons"].get(charge.reason, charge.reason)

    check_in = min(date_range.begin_date for date_range in booking.date_ranges)
    check_out = max(date_range.end_date for date_range in booking.date_ranges)
    address = guest.residence_address

    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, settings.business_name, new_x="LMARGIN", new_y="NEXT")
    if settings.business_address:
        pdf.set_font("Helvetica", "", 10)
        for line in settings.business_address.splitlines():
            pdf.cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, f"{labels['invoice']} {invoice_number_for(charge)}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"{labels['date']}: {charge.created_at.date().isoformat()}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"{labels['booking_reference']}: {booking.id}", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, labels["billed_to"], new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"{guest.first_name} {guest.family_name}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, guest.email, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"{address.street_address}, {address.zip} {address.city}, {address.country}", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(4)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"{labels['stay']}: {check_in.isoformat()} to {check_out.isoformat()}", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(130, 8, labels["description"], border=1)
    pdf.cell(50, 8, labels["amount"], border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(130, 8, charge_description, border=1)
    pdf.cell(50, 8, format_money(charge.amount, charge.currency), border=1, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, f"{labels['payment_reference']}: {charge.stripe_payment_intent_id}", new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
