# POS Integration API — guide for the POS developer

The Customers Platform receives **customers** and **invoices** from every branch's POS.
The POS **pushes** data to the platform over HTTPS/JSON:

1. **Live sync:** send each new or changed customer and each completed, returned or voided invoice
   as it happens (or every few minutes).
2. **History (backfill):** send all previously recorded customers and invoices once, in batches.

Every call is **idempotent**, so it's always safe to resend:
- A customer is matched by **phone number**.
- An invoice is matched by **branch + invoice_no**. Sending the same invoice again *replaces* it and never duplicates it.

Interactive reference (all fields, try it out): `https://<platform-address>/api/docs` → section **POS integration**.

---

## 1. Connection

| | |
|---|---|
| Base URL | `https://<platform-address>/api/v1/pos` (today: `http://187.124.177.138:1100/api/v1/pos`) |
| Format | JSON, UTF-8 (Arabic text is fine) |
| Authentication | header `X-API-Key: cpk_...` |
| Compression (optional) | `Content-Encoding: gzip` on the request body. Recommended for history batches. |

**API keys:** the platform admin creates **one key per branch** in *Settings → POS integration*. Each key
has a default **branch name**, which is used for every invoice/customer sent with that key unless the
payload sets `branch`. A key is shown only once and can be revoked at any time.

> Use HTTPS in production (put the platform behind a domain with a certificate). Over plain HTTP the key
> can be read by anyone on the network path.

---

## 2. Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/ping` | Test the connection and the key |
| POST | `/customers` | Create / update up to **5,000** customers |
| POST | `/invoices` | Create / replace / return / void up to **1,000** invoices |
| DELETE | `/invoices/{invoice_no}?branch=...` | Void (delete) one invoice |
| GET | `/sync-state?branch=...` | What the platform already has: last invoice time, counts |

### 2.1 `GET /ping`
```json
{ "ok": true, "key": "Maadi POS", "branch": "Maadi", "server_time": "2026-11-11T14:35:02" }
```

### 2.2 `POST /customers`
```json
{
  "customers": [
    {
      "phone": "01001112222",
      "first_name": "Sara",
      "last_name": "Ali",
      "name": null,
      "email": "sara@example.com",
      "gender": "F",
      "birth_date": "1990-05-17",
      "region": "Cairo",
      "city": "New Cairo",
      "district": "Fifth Settlement",
      "area": "90 Street",
      "address": "Building 12, 90 Street, Fifth Settlement, New Cairo",
      "branch": "Maadi",
      "registered_at": "2026-11-11T10:02:00",
      "pos_customer_id": "C-000123",
      "extra": { "loyalty_card": "L-5531", "notes": "prefers delivery" }
    }
  ]
}
```

| Field | Required | Notes |
|---|---|---|
| `phone` | **yes** | Any format (`+20 100…`, `100…`, `0100…`). Normalised to `01xxxxxxxxx`. It's the customer's identity. |
| `name` or `first_name` + `last_name` | no | If `name` is empty, it's built from first + last name |
| `registered_at` | recommended | Date+time the customer was created in the POS. Kept from the **first** time it's received. |
| `branch` | no | Branch where the customer registered (defaults to the key's branch). Kept from the first time. |
| `pos_customer_id` | recommended | The customer's ID in the POS database |
| `region`, `city`, `district`, `area`, `address` | no | Used for the area analysis. `district` matters most. |
| `email`, `gender`, `birth_date` | no | |
| `extra` | no | **Any other customer fields** you have (stored as JSON, nothing is lost) |

Empty or `null` fields never erase values the platform already has.

Response:
```json
{ "accepted": 1, "rejected": [ { "index": 3, "phone": "abc", "error": "phone has no digits" } ] }
```

### 2.3 `POST /invoices`
```json
{
  "invoices": [
    {
      "invoice_no": "M-2026-000981",
      "branch": "Maadi",
      "invoice_date": "2026-11-11T14:35:00",
      "status": "completed",
      "customer_phone": "01001112222",
      "customer_name": "Sara Ali",
      "customer_id": "C-000123",
      "sales_type": "Cash",
      "payment_method": "Card",
      "cashier": "Mona",
      "lines": [
        { "item_code": "P1001", "item_name": "Panadol Extra 24 tab", "category": "Medicine",
          "material_group": "Analgesics", "quantity": 2, "unit": "Box", "unit_price": 50,
          "discount": 0, "line_total": 100 },
        { "item_code": "V2001", "item_name": "Vitamin C 1000", "category": "Supplements",
          "quantity": 1, "unit_price": 120, "discount": 20 }
      ],
      "extra": { "pos_terminal": "T2", "insurance_company": null }
    }
  ]
}
```

| Field | Required | Notes |
|---|---|---|
| `invoice_no` | **yes** | Unique **per branch**. Together with `branch`, it's the invoice's identity. |
| `invoice_date` | **yes** | **Date and time**, ISO-8601. Without a time zone it's read as Cairo time; with one (e.g. `+02:00` or `Z`), it's converted to Cairo time. |
| `branch` | yes* | *Optional if the API key has a default branch |
| `status` | no | `completed` (default) · `return` (stored with negative amounts) · `void` (removes the invoice, `lines` can be empty) |
| `customer_phone` | recommended | Links the invoice to the customer. Walk-in sales can omit it (they count in totals, not per customer). |
| `customer_name`, `customer_id` | no | |
| `sales_type` | no | e.g. Cash / Delivery / Insurance. Shown in the reports. |
| `payment_method`, `cashier` | no | Stored in the invoice details |
| `lines[]` | **yes** | One per item |
| `lines[].line_total` | no | **Net** amount of the line. If missing: `quantity × unit_price − discount`. |
| `lines[].quantity` | no | Default 1. For returns, send positive numbers; the platform makes them negative. |
| `extra` / `lines[].extra` | no | Any other data (stored as JSON) |

Response:
```json
{ "accepted": 1, "lines": 2, "rejected": [] }
```
A rejected item doesn't block the others: fix it and send that item again.

**Edits:** if an invoice changes after it was sent, send the **whole invoice again** with the same
`invoice_no`. It replaces the old one.

### 2.4 `DELETE /invoices/{invoice_no}?branch=Maadi`
Same as sending it with `"status": "void"`. Returns `{ "deleted_lines": 2 }`.

### 2.5 `GET /sync-state?branch=Maadi`
```json
{ "branch": "Maadi", "invoices": 182334, "last_invoice_date": "2026-11-11T14:35:00",
  "customers": 80714, "last_registered_at": "2026-11-11T10:02:00", "last_update": "2026-11-11T14:36:10" }
```
Use it after an outage, or to check the backfill.

### Errors
| HTTP | Meaning | What to do |
|---|---|---|
| 200 | Done. Check `rejected[]` for items that were refused. | Fix and resend only those |
| 401 | Missing, wrong or revoked key | Check the key with the platform admin |
| 413 / 422 | Body too large or wrong JSON shape (details in `detail`) | Send smaller batches / fix the field |
| 429, 5xx, timeout, no network | Temporary | Retry later with back-off (1 s, 2 s, 4 s … max 5 min). It's safe to resend. |

---

## 3. Live sync (recommended design)

Use an **outbox** in the POS database, so nothing is lost when the internet is down:

1. When an invoice is saved, returned or voided, or a customer is created or edited, insert a row into an outbox
   table **in the same transaction**:
   ```sql
   CREATE TABLE platform_outbox (
     id          BIGINT IDENTITY PRIMARY KEY,
     entity      VARCHAR(20)  NOT NULL,   -- 'invoice' | 'customer'
     entity_key  VARCHAR(100) NOT NULL,   -- invoice_no or phone
     created_at  DATETIME     NOT NULL DEFAULT GETDATE(),
     sent_at     DATETIME     NULL,
     attempts    INT          NOT NULL DEFAULT 0,
     last_error  NVARCHAR(1000) NULL
   );
   ```
   (Adapt the types to your database.)
2. A background worker (Windows service or timer in the POS app), every 30–60 seconds:
   - reads up to 500 unsent rows, oldest first;
   - loads the current customer or invoice data and sends one `POST /customers` and one `POST /invoices`;
   - marks the accepted rows as sent and stores the error on rejected ones.
3. If the call fails (no network, 5xx), it leaves the rows unsent and tries again on the next round.

---

## 4. Sending all previously recorded data (backfill)

Run once per branch (or once for all branches with `branch` set on each invoice):

1. **Customers first:** read all customers ordered by registration date, and send them in batches of 2,000–5,000
   (gzip). Include `registered_at` and `pos_customer_id`.
2. **Then invoices, oldest → newest:** batches of **500–1,000 invoices** with all their lines, ordered by
   `invoice_date`. Keep a checkpoint (last invoice date/id sent) in a local file or table.
3. On a crash, restart from the checkpoint. Overlap doesn't matter, because invoices are matched by
   branch + invoice_no and resending replaces instead of duplicating.
4. Check: `GET /sync-state` should report the same number of invoices as the POS.
5. Then start the live sync (section 3). Start it **before** the backfill finishes if you like:
   both can run at the same time.

Speed guide: ~1,000 invoices (≈3–5k lines) per request takes about 1–2 s on the platform.
One million invoices ≈ 1,000 requests ≈ 30–60 minutes.

Example SQL to read history (adapt table and column names):
```sql
SELECT h.InvoiceNo, h.BranchName, h.InvoiceDateTime, h.Status, h.CustomerPhone, h.CustomerName,
       h.SalesType, h.PaymentMethod, h.CashierName,
       d.ItemCode, d.ItemName, d.Category, d.Qty, d.Unit, d.UnitPrice, d.Discount, d.NetAmount
FROM   InvoiceHeader h JOIN InvoiceDetail d ON d.InvoiceId = h.Id
WHERE  h.InvoiceDateTime > @checkpoint
ORDER  BY h.InvoiceDateTime, h.Id
-- group the rows by invoice in C# and send 1,000 invoices per request
```

---

## 5. C# (.NET 6+) client

```csharp
using System.IO.Compression;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

public sealed class PlatformClient : IDisposable
{
    private readonly HttpClient _http;
    private static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,       // invoice_no, line_total, ...
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    };

    public PlatformClient(string baseUrl, string apiKey)
    {
        _http = new HttpClient { BaseAddress = new Uri(baseUrl.TrimEnd('/') + "/"), Timeout = TimeSpan.FromSeconds(120) };
        _http.DefaultRequestHeaders.Add("X-API-Key", apiKey);
    }

    public Task<PushResult> SendInvoicesAsync(IEnumerable<Invoice> invoices, CancellationToken ct = default)
        => PostAsync("invoices", new { invoices }, ct);

    public Task<PushResult> SendCustomersAsync(IEnumerable<Customer> customers, CancellationToken ct = default)
        => PostAsync("customers", new { customers }, ct);

    private async Task<PushResult> PostAsync(string path, object body, CancellationToken ct)
    {
        byte[] raw = JsonSerializer.SerializeToUtf8Bytes(body, Json);
        for (int attempt = 0; ; attempt++)
        {
            try
            {
                using var gz = new MemoryStream();
                using (var z = new GZipStream(gz, CompressionLevel.Fastest, leaveOpen: true)) z.Write(raw);
                var content = new ByteArrayContent(gz.ToArray());
                content.Headers.ContentType = new MediaTypeHeaderValue("application/json") { CharSet = "utf-8" };
                content.Headers.ContentEncoding.Add("gzip");

                using var res = await _http.PostAsync(path, content, ct);
                if ((int)res.StatusCode == 401) throw new InvalidOperationException("API key rejected");
                if (res.IsSuccessStatusCode)
                    return (await res.Content.ReadFromJsonAsync<PushResult>(Json, ct))!;
                if ((int)res.StatusCode is 400 or 413 or 422)            // our data is wrong: don't retry blindly
                    throw new InvalidOperationException(await res.Content.ReadAsStringAsync(ct));
            }
            catch (HttpRequestException) when (attempt < 8) { }        // network down -> retry
            catch (TaskCanceledException) when (!ct.IsCancellationRequested && attempt < 8) { }
            await Task.Delay(TimeSpan.FromSeconds(Math.Min(300, Math.Pow(2, attempt))), ct);
        }
    }

    public void Dispose() => _http.Dispose();
}

public record Customer(string Phone, string? FirstName = null, string? LastName = null, string? Name = null,
    string? Email = null, string? Gender = null, DateOnly? BirthDate = null, string? Region = null,
    string? City = null, string? District = null, string? Area = null, string? Address = null,
    string? Branch = null, DateTime? RegisteredAt = null, string? PosCustomerId = null,
    Dictionary<string, object?>? Extra = null);

public record InvoiceLine(string? ItemCode, string? ItemName, decimal Quantity, decimal? UnitPrice,
    decimal Discount = 0, decimal? LineTotal = null, string? Category = null, string? MaterialGroup = null,
    string? Unit = null, Dictionary<string, object?>? Extra = null);

public record Invoice(string InvoiceNo, DateTime InvoiceDate, List<InvoiceLine> Lines,
    string Status = "completed", string? Branch = null, string? CustomerPhone = null,
    string? CustomerName = null, string? CustomerId = null, string? SalesType = null,
    string? PaymentMethod = null, string? Cashier = null, Dictionary<string, object?>? Extra = null);

public record Rejected(int Index, string? InvoiceNo, string? Phone, string Error);
public record PushResult(int Accepted, int? Lines, List<Rejected> Rejected);
```

Usage:
```csharp
using var platform = new PlatformClient("http://187.124.177.138:1100/api/v1/pos", "cpk_...");

// live: after saving an invoice
var result = await platform.SendInvoicesAsync(new[] {
    new Invoice("M-2026-000981", DateTime.Now, new() {
        new InvoiceLine("P1001", "Panadol Extra 24 tab", 2, 50m),
        new InvoiceLine("V2001", "Vitamin C 1000", 1, 120m, Discount: 20m),
    }, CustomerPhone: "01001112222", CustomerName: "Sara Ali", SalesType: "Cash")
});

// backfill: 1,000 invoices per request, oldest first
foreach (var batch in historicalInvoices.Chunk(1000))
{
    var r = await platform.SendInvoicesAsync(batch);
    SaveCheckpoint(batch.Last().InvoiceDate);
    foreach (var bad in r.Rejected) Log($"{bad.InvoiceNo}: {bad.Error}");
}
```

> `JsonNamingPolicy.SnakeCaseLower` needs .NET 8. On older .NET, add
> `[JsonPropertyName("invoice_no")]` and so on to the properties, or use Newtonsoft.Json with `SnakeCaseNamingStrategy`.

---

## 6. Test checklist
1. `GET /ping` with the key → `ok: true`.
2. Send 1 customer and 1 invoice → open the platform → *Transactions*, search the phone.
3. Send the same invoice again → still one invoice (no duplicate).
4. Send it with `"status": "return"` and a new invoice_no → the amount appears negative.
5. Send `"status": "void"` → the invoice disappears.
6. Disconnect the network, make sales, reconnect → everything arrives through the outbox.
