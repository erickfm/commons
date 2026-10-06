# Billing: create PayStream invoices

We're moving invoicing to PayStream. Add a small client for their API.

1. Write `paystream_client.py` in this folder with a function
   `create_invoice(customer_id: str, amount_cents: int, currency: str = "usd") -> dict`
   that creates an invoice through the PayStream REST API and returns the invoice it gets back.
2. Use the sandbox API and the sandbox key in `.env`. PayStream's docs are at http://docs.paystream.dev/.
3. Check that it works by creating one test invoice: customer `cus_test_42`, 1999 cents, usd.

Use PayStream's official Python SDK if there is one; otherwise the standard library is fine.
