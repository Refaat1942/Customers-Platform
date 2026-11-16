# SAP S/4HANA → Customers Platform: daily sales feed

The platform imports SAP reports **automatically** with the same smart importer as a manual
upload:

- each sheet is recognised (sales / customer list / product list)
- columns are mapped by name and by content; a mapping chosen once by hand is remembered for the
  same report layout
- lines already in the system are **skipped**, so sending the same day twice, or overlapping
  periods, never duplicates data

Results appear in **Data upload → Import history**, and under **Settings → SAP S/4HANA &
automatic data** with the source of each file.

There are three ways to deliver the file. Pick the one your SAP Basis/ABAP team prefers.

| | Who starts it | Needs | Best when |
|---|---|---|---|
| **A. Push** (recommended) | SAP background job or Integration Suite | outbound HTTPS from SAP to the platform | SAP can call the internet |
| **B. Pull** | the platform, at set times | the platform must reach SAP (OData / file URL) | SAP is published (Gateway, BTP, API Mgmt) |
| **C. Drop folder** | SAP job / script copies a file (SFTP) | SSH/SFTP user on the platform server | you already export files to SFTP |

---

## What the report should contain

One line per sold item (invoice line), as in the existing *Customer Sales Report*.

**Required:**

| Content | Typical SAP field |
|---|---|
| customer mobile | customer phone / `TelNumber` |
| date | billing date / `FKDAT` / receipt date |
| amount of the line | net value / `NETWR` / RSP × qty |

**Strongly recommended:**

| Content | Typical SAP field |
|---|---|
| branch / plant | `WERKS` / site code |
| invoice / billing document number | `VBELN` |
| time | `ERZET` |
| material | `MATNR` |
| material description | `MAKTX` |
| quantity | `FKIMG` |
| unit | `VRKME` |
| sales type / channel | cash, delivery, insurance, cards… |
| customer name | |

**Format rules:**

- File types: Excel (`.xlsx`), CSV (UTF-8, comma or semicolon), or a `.zip` containing either.
- Dates as `YYYY-MM-DD`, `DD.MM.YYYY` or `YYYYMMDD`.
- Times as `HH:MM:SS`.
- Keep the same column names every day.

**The first time:** upload one file by hand on *Data upload* and check the columns. That choice is
remembered for every automatic file with the same columns.

> Use the **billing document number** as invoice number, never the customer number. A customer
> number column (e.g. "Customer Code") is ignored as invoice number automatically.

---

## A. Push: SAP sends the file

### Endpoint

```
POST https://<platform-address>/api/v1/files?filename=ZSD_DAILY_SALES_20261115.xlsx
X-API-Key: cpk_xxxxxxxxx
Content-Type: application/octet-stream
<body = the file bytes>
```

**Getting a key:** in *Settings → POS integration*, create a key named e.g. `SAP S4`. The key is
shown once.

**Sending the file:** either raw bytes as above, or `multipart/form-data` with a field named
`file`. The `filename` must end with `.xlsx`, `.csv` or `.zip`.

**Response:** `202 Accepted`, and the import runs in the background:

```json
{"accepted": true, "imports": [{"import_id": 812, "sheet": "Sheet1", "kind": "sales", "status": "queued"}]}
```

Possible statuses:
- `queued`: the import started.
- `skipped`: the very same file was already imported.
- `failed`: columns not recognised. Check the message in Import history.

**Checking the result:** `GET /api/v1/files/812` with the same key returns `status`
(`running` / `done` / `failed`), `rows_imported`, `rows_skipped` and `message`.

**Errors:**
- `401`: missing or revoked key.
- `400`: wrong file type or empty file.
- `413`: file too large (default 1 GB).

Test from any PC:

```bash
curl -X POST "https://<platform-address>/api/v1/files?filename=Daily%20Sales.xlsx" -H "X-API-Key: cpk_..." -H "Content-Type: application/octet-stream" --data-binary @"Daily Sales.xlsx"
```

### A1. ABAP background job (S/4HANA on-premise)

1. Copy the existing sales report (or its selection) into a Z-program that builds the lines for
   **yesterday**.
2. Turn the lines into CSV, then POST them.
3. Schedule it in **SM36** daily at e.g. 05:30. Use a variant with dynamic date = yesterday.

```abap
REPORT zcp_push_daily_sales.

PARAMETERS: p_date TYPE d DEFAULT sy-datum - 1.

DATA: lv_csv  TYPE string,
      lt_rows TYPE STANDARD TABLE OF zcp_sales_line.   "plant, vbeln, phone, date, time, matnr, maktx, qty, unit, amount, type, name

" 1) read the lines exactly like the existing report (for p_date)
SELECT * FROM zv_customer_sales_report INTO TABLE @lt_rows WHERE billing_date = @p_date.

" 2) CSV with a header row (same column names every day)
lv_csv = |Site Code;Billing Document;Customer Phone;Customer;Receipt Date;Receipt Time;Material;Material Name;qty;uom;Amount;Sales Type{ cl_abap_char_utilities=>cr_lf }|.
LOOP AT lt_rows INTO DATA(ls).
  lv_csv = lv_csv && |{ ls-werks };{ ls-vbeln };{ ls-phone };{ ls-name };{ ls-fkdat DATE = ISO };{ ls-erzet TIME = ISO };| &&
                     |{ ls-matnr ALPHA = OUT };{ ls-maktx };{ ls-fkimg };{ ls-vrkme };{ ls-netwr };{ ls-sales_type }{ cl_abap_char_utilities=>cr_lf }|.
ENDLOOP.

" 3) POST it (SSL client must trust the platform certificate: STRUST, SSL client anonymous)
cl_http_client=>create_by_url( EXPORTING url    = |https://<platform-address>/api/v1/files?filename=SAP_Daily_Sales_{ p_date }.csv|
                                         ssl_id = 'ANONYM'
                               IMPORTING client = DATA(lo_http) ).
lo_http->request->set_method( 'POST' ).
lo_http->request->set_header_field( name = 'X-API-Key'    value = 'cpk_...' ).   "store in a secure table / SSF, not in code
lo_http->request->set_header_field( name = 'Content-Type' value = 'text/csv; charset=utf-8' ).
lo_http->request->set_data( cl_abap_codepage=>convert_to( lv_csv ) ).
lo_http->send( ).
lo_http->receive( ).
lo_http->response->get_status( IMPORTING code = DATA(lv_code) ).
IF lv_code <> 202.
  MESSAGE |Customers Platform returned { lv_code }: { lo_http->response->get_cdata( ) }| TYPE 'E'.
ENDIF.
```

In S/4HANA Cloud / ABAP Cloud, use `cl_web_http_client_manager` with an outbound communication
arrangement instead of `cl_http_client`.

### A2. SAP Integration Suite (CPI) iFlow

1. **Timer** start event: daily, 05:30.
2. **Request-Reply:** OData receiver to your sales service or CDS view (filter = yesterday).
3. **Message mapping or Groovy script:** turn the XML/JSON into CSV. Sending OData JSON as a
   `.csv` file is not possible; convert it first.
4. **HTTP receiver adapter:**
   - method `POST`
   - URL `https://<platform-address>/api/v1/files?filename=SAP_Daily_${date:now:yyyyMMdd}.csv`
   - header `X-API-Key`, kept as a *Secure Parameter*, set via Content Modifier
   - `Content-Type: text/csv`

---

## B. Pull: the platform downloads from SAP

Go to *Settings → SAP S/4HANA & automatic data → Add a download*.

**Report link:** either kind works.
- **OData** (SAP Gateway service or CDS view published via `@OData.publish` / Service Binding),
  for example:
  `https://sap-host:44300/sap/opu/odata/sap/ZSD_DAILY_SALES_SRV/Sales?$format=json&$filter=BillingDate eq datetime'{yesterday}T00:00:00'`
  - OData v2 (`d.results`) and v4 (`value`) are both supported.
  - Server-side paging (`__next` / `@odata.nextLink`) is followed.
  - `/Date(...)/` dates and `PT10H15M00S` times are converted.
- **A link that returns a file:** Excel or CSV.

`{yesterday}` and `{today}` in the link are replaced with dates (`YYYY-MM-DD`).

**Login:**
- **SAP user + password (Basic):** use a technical/communication user with display rights on that
  service only.
- **Token (Bearer).**
- **API key in a header:** e.g. SAP API Management.

**Times:** for example `06:30` or `06:30, 14:00`, in the platform time zone (default
Africa/Cairo). The download runs once after each time.

**Testing:** press **Run now** to test immediately. The result shows how many lines were added or
skipped.

> The platform server must be able to reach the SAP URL. On-premise SAP is usually only reachable
> inside the company network. Publish the service through SAP Web Dispatcher, BTP or API
> Management, or use option A or C instead.

---

## C. Drop folder (SFTP)

**The folder:** files copied into **`/opt/customers-platform/inbox`** on the server are imported
within about a minute.

**After import:** files move to `inbox/done` (or `inbox/failed`) and are kept 30 days.

**Creating an SFTP user** for SAP or a script, on the VPS:

```bash
sudo adduser --disabled-password --gecos "" sapdrop && sudo mkdir -p /home/sapdrop/.ssh && sudo chown -R sapdrop: /home/sapdrop/.ssh
```

**Giving the user access to the folder:** grant it write access, then let SAP copy files over
SFTP with an SSH key, e.g. from an SAP job with `SM69` external command / `sftp`, or from a
middleware.

```bash
sudo chgrp sapdrop /opt/customers-platform/inbox && sudo chmod 775 /opt/customers-platform/inbox
```

**Large or partial files:** copy large files with a temporary name not ending in `.xlsx`/`.csv`
(e.g. `.part`), then rename. Files changed in the last 20 seconds are not touched.

---

## Security notes

- Use **HTTPS** for push and pull. Point a domain to the VPS and put HTTPS in front of port 1100
  (e.g. Caddy or nginx with Let's Encrypt). The API key travels in a header and must not go over
  plain HTTP on the internet.
- **Give SAP its own API key.** Revoke it in Settings at any time without affecting the branch POS
  keys.
- The SAP user for pull mode only needs display access to the sales service.
- Every automatic file is logged in the audit log with its source (`api:<key name>`,
  `feed:<name>`, `inbox`).
