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

There are three ways to deliver the file. The **easiest is the SE24 class described next**: it
exports your existing Z report as it is, and can push (A) or be pulled (B).

| | Who starts it | Needs | Best when |
|---|---|---|---|
| **A. Push** (recommended) | SAP background job or Integration Suite | outbound HTTPS from SAP to the platform | SAP can call the internet |
| **B. Pull** | the platform, at set times | the platform must reach SAP (OData / file URL) | SAP is published (Gateway, BTP, API Mgmt) |
| **C. Drop folder** | SAP job / script copies a file (SFTP) | SSH/SFTP user on the platform server | you already export files to SFTP |

---

## Recommended: one SE24 class that exports the existing Z report

No new report is needed. The class **`ZCL_CP_ZREPORT_EXPORT`** (create it in **SE24**) runs your
existing Z sales report in the background. It captures the table the report would show in its
ALV, using `CL_SALV_BS_RUNTIME_INFO`, and turns it into a CSV file the platform reads directly:

- semicolon separated, UTF-8 (Arabic names are kept)
- first row = the column titles users already see (DDIC long texts)
- dates `YYYY-MM-DD`, times `HH:MM:SS`, amounts `1234.50` (minus sign in front for returns)
- material / document numbers without leading zeros (conversion exits ALPHA / MATN1), so they
  match the product list; phone numbers keep their leading 0

The same class works both ways. Choose one.

### Way 1: SAP sends the report every morning (push)

1. **SE24:** create class `ZCL_CP_ZREPORT_EXPORT` from the code in *Appendix 1*.
2. **SE38:** create program `ZCP_PUSH_DAILY` from *Appendix 2*.
3. **SM59:** create HTTP destination `ZCP_PLATFORM` (type G):
   - host = the platform's address, port 443
   - path prefix `/api/v1/files`
   - *SSL active* (client certificate: ANONYM)
4. **STRUST:** import the platform's HTTPS certificate chain into *SSL client Anonymous*.
5. **STVARV:** create parameter `ZCP_API_KEY` with the key from *Customers Platform → Settings →
   POS integration* (create a key named `SAP`).
6. **SE38 → ZCP_PUSH_DAILY:** run it once by hand. The message must say *Sent to Customers
   Platform*, and the file appears in *Data upload → Import history*. Parameters:
   - `P_REP` = your Z report (e.g. `ZSD_CUSTOMER_SALES`)
   - `P_VAR` = a variant (optional)
   - `P_DFLD` = the report's date select-option (e.g. `S_FKDAT`)
   - `P_DAYS` = 1
7. **SM36:** schedule `ZCP_PUSH_DAILY` with that variant daily at e.g. 05:30. Errors end the job
   in red in **SM37**.

`P_DAYS = 7` resends the last week. Lines already in the platform are skipped, so this safely
fills any missed day.

### Way 2: the platform downloads the report (pull)

1. **SE24:** create class `ZCL_CP_ZREPORT_EXPORT` (*Appendix 1*).
2. **SICF:** create service `/sap/zcp_export`:
   - handler list: `ZCL_CP_ZREPORT_EXPORT`
   - logon data: a technical user with authority for the report only
   - activate the service
3. **STVARV:** create parameter `ZCP_REPORTS` = the reports allowed through this service,
   comma separated, no spaces (e.g. `ZSD_CUSTOMER_SALES`).
4. **Customers Platform → Settings → SAP S/4HANA & automatic data → Add a download:**
   - **URL:**
     `https://<sap-host>:<port>/sap/zcp_export?sap-client=100&report=ZSD_CUSTOMER_SALES&datefield=S_FKDAT&from={yesterday}&to={yesterday}`
     (add `&variant=CP_DAILY` to use a variant)
   - **Login:** SAP user + password of the technical user
   - **Times:** e.g. `06:30`
   - Press **Run now** to test.

This needs the platform server to reach the SAP host (see option B below).

> `CL_SALV_BS_RUNTIME_INFO` works for reports that show their result with `CL_SALV_TABLE` or
> `REUSE_ALV_GRID_DISPLAY` / `REUSE_ALV_LIST_DISPLAY`. If the Z report draws the ALV in a custom
> container (`CL_GUI_ALV_GRID`), move its SELECT into a method and call that instead of SUBMIT.
> The rest of the class (CSV, push, SICF) stays the same.

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

---

## Appendix 1: class ZCL_CP_ZREPORT_EXPORT (SE24, source-code based)

Also in the project: `docs/sap/ZCL_CP_ZREPORT_EXPORT.abap`.

```abap
"! Customers Platform - export any Z report (ALV) as CSV.
"!
"! Runs the Z report in the background, takes the table it would show in the ALV
"! (CL_SALV_BS_RUNTIME_INFO), and turns it into a CSV file:
"!   - semicolon separated, UTF-8, first row = the column titles users see (DDIC long text, EN)
"!   - dates YYYY-MM-DD, times HH:MM:SS, numbers 1234.50 (minus sign in front)
"!   - material / customer / document numbers without leading zeros (ALPHA, MATN1)
"!
"! Two ways to use it:
"!   PUSH: program ZCP_PUSH_DAILY (daily job in SM36) calls GET_CSV + PUSH
"!   PULL: register this class as HTTP handler in SICF; the platform downloads the CSV
"!
"! Settings (transaction STVARV, type Parameter):
"!   ZCP_API_KEY  the key created in Customers Platform > Settings > POS integration (push)
"!   ZCP_REPORTS  reports allowed through SICF, comma separated, no spaces (pull)
"! HTTP destination (SM59, type G): ZCP_PLATFORM -> host of the platform, path prefix /api/v1/files
CLASS zcl_cp_zreport_export DEFINITION
  PUBLIC
  FINAL
  CREATE PUBLIC.

  PUBLIC SECTION.
    INTERFACES if_http_extension.

    TYPES ty_params TYPE STANDARD TABLE OF rsparams WITH EMPTY KEY.

    "! Runs the report (variant and/or selections) and returns its ALV output as CSV
    "! (empty string when the report shows no list, e.g. no data for the selection)
    CLASS-METHODS get_csv
      IMPORTING iv_report     TYPE syrepid
                iv_variant    TYPE rsvar-variant OPTIONAL
                it_params     TYPE ty_params OPTIONAL
      RETURNING VALUE(rv_csv) TYPE string.

    "! Sends the CSV to the Customers Platform through SM59 destination ZCP_PLATFORM.
    "! Returns the HTTP status: 202 = accepted (the import runs in the platform)
    CLASS-METHODS push
      IMPORTING iv_csv           TYPE string
                iv_filename      TYPE string
      EXPORTING ev_message       TYPE string
      RETURNING VALUE(rv_status) TYPE i.

    "! Selection for the report's date select-option, e.g. S_FKDAT from..to
    CLASS-METHODS date_param
      IMPORTING iv_field         TYPE rsscr_name
                iv_from          TYPE d
                iv_to            TYPE d
      RETURNING VALUE(rt_params) TYPE ty_params.

  PRIVATE SECTION.
    CONSTANTS c_sep TYPE c LENGTH 1 VALUE ';'.

    CLASS-METHODS to_csv
      IMPORTING ir_data       TYPE REF TO data
      RETURNING VALUE(rv_csv) TYPE string.

    CLASS-METHODS cell
      IMPORTING iv_value TYPE any
                io_elem  TYPE REF TO cl_abap_elemdescr
      RETURNING VALUE(rv) TYPE string.

    CLASS-METHODS quote
      IMPORTING iv_text TYPE string
      RETURNING VALUE(rv) TYPE string.

    CLASS-METHODS setting
      IMPORTING iv_name TYPE rvari_vnam
      RETURNING VALUE(rv) TYPE string.
ENDCLASS.



CLASS zcl_cp_zreport_export IMPLEMENTATION.

  METHOD get_csv.
    DATA lr_data TYPE REF TO data.

    " the report runs normally, but its ALV is not displayed: the data is kept for us
    cl_salv_bs_runtime_info=>set( display  = abap_false
                                  metadata = abap_false
                                  data     = abap_true ).
    IF iv_variant IS NOT INITIAL.
      SUBMIT (iv_report) USING SELECTION-SET iv_variant
                         WITH SELECTION-TABLE it_params
                         AND RETURN.
    ELSE.
      SUBMIT (iv_report) WITH SELECTION-TABLE it_params
                         AND RETURN.
    ENDIF.

    TRY.
        cl_salv_bs_runtime_info=>get_data_ref( IMPORTING r_data = lr_data ).
      CATCH cx_salv_bs_sc_runtime_info.
        CLEAR lr_data.                       " no list shown (no data for the selection)
    ENDTRY.
    cl_salv_bs_runtime_info=>clear_all( ).

    rv_csv = to_csv( lr_data ).
  ENDMETHOD.


  METHOD to_csv.
    FIELD-SYMBOLS: <lt_data> TYPE ANY TABLE,
                   <ls_row>  TYPE any,
                   <lv>      TYPE any.
    DATA: lt_lines TYPE string_table,
          lt_cells TYPE string_table,
          lt_comp  TYPE abap_component_view_tab,
          ls_dfies TYPE dfies.

    CHECK ir_data IS BOUND.
    ASSIGN ir_data->* TO <lt_data>.
    CHECK <lt_data> IS ASSIGNED AND <lt_data> IS NOT INITIAL.

    DATA(lo_table)  = CAST cl_abap_tabledescr( cl_abap_typedescr=>describe_by_data( <lt_data> ) ).
    DATA(lo_struct) = CAST cl_abap_structdescr( lo_table->get_table_line_type( ) ).
    " all fields (includes flattened); only simple fields, no nested tables / references
    LOOP AT lo_struct->get_included_view( ) INTO DATA(ls_any).
      IF ls_any-type->kind = cl_abap_typedescr=>kind_elem.
        APPEND ls_any TO lt_comp.
      ENDIF.
    ENDLOOP.

    " header row: the column titles users know (DDIC long text in English), else the field name
    LOOP AT lt_comp INTO DATA(ls_comp).
      DATA(lv_head) = CONV string( ls_comp-name ).
      DATA(lo_elem) = CAST cl_abap_elemdescr( ls_comp-type ).
      IF lo_elem->is_ddic_type( ) = abap_true.
        CLEAR ls_dfies.
        lo_elem->get_ddic_field( EXPORTING  p_langu    = 'E'
                                 RECEIVING  p_flddescr = ls_dfies
                                 EXCEPTIONS OTHERS     = 1 ).
        IF sy-subrc = 0 AND ls_dfies-scrtext_l IS NOT INITIAL.
          lv_head = ls_dfies-scrtext_l.
        ENDIF.
      ENDIF.
      APPEND quote( lv_head ) TO lt_cells.
    ENDLOOP.
    APPEND concat_lines_of( table = lt_cells sep = c_sep ) TO lt_lines.

    " one row per line of the report
    LOOP AT <lt_data> ASSIGNING <ls_row>.
      CLEAR lt_cells.
      LOOP AT lt_comp INTO ls_comp.
        ASSIGN COMPONENT ls_comp-name OF STRUCTURE <ls_row> TO <lv>.
        IF sy-subrc = 0.
          APPEND cell( iv_value = <lv> io_elem = CAST #( ls_comp-type ) ) TO lt_cells.
        ELSE.
          APPEND `` TO lt_cells.
        ENDIF.
      ENDLOOP.
      APPEND concat_lines_of( table = lt_cells sep = c_sep ) TO lt_lines.
    ENDLOOP.

    rv_csv = concat_lines_of( table = lt_lines sep = cl_abap_char_utilities=>cr_lf )
             && cl_abap_char_utilities=>cr_lf.
  ENDMETHOD.


  METHOD cell.
    CASE io_elem->type_kind.
      WHEN cl_abap_typedescr=>typekind_date.
        IF iv_value IS INITIAL.
          rv = ``.
        ELSE.
          rv = |{ CONV d( iv_value ) DATE = ISO }|.                 " 2026-11-15
        ENDIF.
      WHEN cl_abap_typedescr=>typekind_time.
        rv = |{ CONV t( iv_value ) TIME = ISO }|.                     " 10:15:00
      WHEN cl_abap_typedescr=>typekind_packed  OR cl_abap_typedescr=>typekind_float
        OR cl_abap_typedescr=>typekind_int     OR cl_abap_typedescr=>typekind_int1
        OR cl_abap_typedescr=>typekind_int2    OR cl_abap_typedescr=>typekind_int8
        OR cl_abap_typedescr=>typekind_decfloat16 OR cl_abap_typedescr=>typekind_decfloat34.
        rv = |{ iv_value }|.                                          " 1234.50 / -90.00
      WHEN cl_abap_typedescr=>typekind_char OR cl_abap_typedescr=>typekind_num
        OR cl_abap_typedescr=>typekind_string.
        IF io_elem->edit_mask CS 'ALPHA' OR io_elem->edit_mask CS 'MATN1'.
          rv = |{ iv_value ALPHA = OUT }|.                            " 000000000000100201 -> 100201
        ELSE.
          rv = |{ iv_value }|.                                        " phones keep their leading 0
        ENDIF.
        CONDENSE rv.
      WHEN OTHERS.
        rv = |{ iv_value }|.
    ENDCASE.
    rv = quote( rv ).
  ENDMETHOD.


  METHOD quote.
    rv = iv_text.
    IF rv CA |;"\r\n|.
      REPLACE ALL OCCURRENCES OF `"` IN rv WITH `""`.
      rv = |"{ rv }"|.
    ENDIF.
  ENDMETHOD.


  METHOD push.
    DATA lo_http TYPE REF TO if_http_client.

    cl_http_client=>create_by_destination( EXPORTING  destination = 'ZCP_PLATFORM'
                                           IMPORTING  client      = lo_http
                                           EXCEPTIONS OTHERS      = 1 ).
    IF sy-subrc <> 0.
      ev_message = `SM59 destination ZCP_PLATFORM is missing or wrong`.
      RETURN.
    ENDIF.

    cl_http_utility=>set_request_uri(
      request = lo_http->request
      uri     = |?filename={ cl_http_utility=>escape_url( iv_filename ) }| ).
    lo_http->request->set_method( if_http_request=>co_request_method_post ).
    lo_http->request->set_header_field( name = 'X-API-Key' value = setting( 'ZCP_API_KEY' ) ).
    lo_http->request->set_content_type( 'text/csv; charset=utf-8' ).
    lo_http->request->set_data( cl_abap_codepage=>convert_to( source = iv_csv codepage = `UTF-8` ) ).

    lo_http->send( EXCEPTIONS OTHERS = 1 ).
    IF sy-subrc = 0.
      lo_http->receive( EXCEPTIONS OTHERS = 1 ).
    ENDIF.
    IF sy-subrc <> 0.
      lo_http->get_last_error( IMPORTING message = ev_message ).
      lo_http->close( ).
      RETURN.
    ENDIF.

    lo_http->response->get_status( IMPORTING code = rv_status ).
    ev_message = lo_http->response->get_cdata( ).
    lo_http->close( ).
  ENDMETHOD.


  METHOD date_param.
    rt_params = VALUE #( ( selname = iv_field kind = 'S' sign = 'I' option = 'BT'
                           low = iv_from high = iv_to ) ).
  ENDMETHOD.


  METHOD setting.
    SELECT SINGLE low FROM tvarvc INTO @DATA(lv_low)
      WHERE name = @iv_name AND type = 'P'.
    rv = condense( CONV string( lv_low ) ).
  ENDMETHOD.


  METHOD if_http_extension~handle_request.
    " PULL - the platform calls (SICF service /sap/zcp_export):
    "   /sap/zcp_export?sap-client=100&report=ZSD_CUSTOMER_SALES&variant=CP_DAILY
    "                  &datefield=S_FKDAT&from=2026-11-15&to=2026-11-15
    DATA lt_params TYPE ty_params.
    DATA lt_allowed TYPE string_table.
    DATA(lv_report)  = to_upper( server->request->get_form_field( 'report' ) ).
    DATA(lv_allowed) = to_upper( setting( 'ZCP_REPORTS' ) ).
    SPLIT lv_allowed AT ',' INTO TABLE lt_allowed.
    IF lv_report IS INITIAL OR NOT line_exists( lt_allowed[ table_line = lv_report ] ).
      server->response->set_status( code = 403 reason = 'Report not allowed' ).
      server->response->set_cdata( |Report { lv_report } is not listed in STVARV parameter ZCP_REPORTS| ).
      RETURN.
    ENDIF.

    DATA(lv_from) = replace( val = server->request->get_form_field( 'from' ) sub = `-` with = `` occ = 0 ).
    DATA(lv_to)   = replace( val = server->request->get_form_field( 'to' )   sub = `-` with = `` occ = 0 ).
    DATA(lv_field) = to_upper( server->request->get_form_field( 'datefield' ) ).
    IF lv_field IS NOT INITIAL AND lv_from IS NOT INITIAL.
      lt_params = date_param( iv_field = CONV #( lv_field )
                              iv_from  = CONV #( lv_from )
                              iv_to    = COND d( WHEN lv_to IS INITIAL THEN lv_from ELSE lv_to ) ).
    ENDIF.

    DATA(lv_csv) = get_csv( iv_report  = CONV #( lv_report )
                            iv_variant = CONV #( to_upper( server->request->get_form_field( 'variant' ) ) )
                            it_params  = lt_params ).

    server->response->set_header_field( name = 'Content-Type' value = 'text/csv; charset=utf-8' ).
    server->response->set_header_field( name  = 'Content-Disposition'
                                        value = |attachment; filename="{ lv_report }_{ lv_from }.csv"| ).
    server->response->set_data( cl_abap_codepage=>convert_to( source = lv_csv codepage = `UTF-8` ) ).
    server->response->set_status( code = 200 reason = 'OK' ).
  ENDMETHOD.

ENDCLASS.
```

## Appendix 2: program ZCP_PUSH_DAILY (SE38)

Also in the project: `docs/sap/ZCP_PUSH_DAILY.abap`.

```abap
*&---------------------------------------------------------------------*
*& ZCP_PUSH_DAILY - send a Z report to the Customers Platform
*& Schedule in SM36 every morning (e.g. 05:30) with a variant.
*& P_DAYS = 1 sends yesterday; 7 resends the last week (lines already in the
*& platform are skipped, nothing is duplicated).
*&---------------------------------------------------------------------*
REPORT zcp_push_daily.

PARAMETERS: p_rep  TYPE syrepid DEFAULT 'ZSD_CUSTOMER_SALES' OBLIGATORY, " the Z report
            p_var  TYPE rsvar-variant,                                  " its variant (optional)
            p_dfld TYPE rsscr_name DEFAULT 'S_FKDAT',                   " its date select-option
            p_days TYPE i DEFAULT 1.                                    " how many days back

START-OF-SELECTION.
  DATA lv_msg TYPE string.

  DATA(lv_to)   = CONV d( sy-datum - 1 ).
  DATA(lv_from) = CONV d( sy-datum - p_days ).

  DATA(lt_params) = COND zcl_cp_zreport_export=>ty_params(
    WHEN p_dfld IS NOT INITIAL
    THEN zcl_cp_zreport_export=>date_param( iv_field = p_dfld iv_from = lv_from iv_to = lv_to ) ).

  DATA(lv_csv) = zcl_cp_zreport_export=>get_csv( iv_report  = p_rep
                                                 iv_variant = p_var
                                                 it_params  = lt_params ).
  IF lv_csv IS INITIAL.
    MESSAGE |{ p_rep }: no data for { lv_from DATE = ISO } - { lv_to DATE = ISO }| TYPE 'S'.
    RETURN.
  ENDIF.

  DATA(lv_status) = zcl_cp_zreport_export=>push(
    EXPORTING iv_csv      = lv_csv
              iv_filename = |{ p_rep }_{ lv_from DATE = ISO }_{ lv_to DATE = ISO }.csv|
    IMPORTING ev_message  = lv_msg ).

  IF lv_status = 202.
    MESSAGE |Sent to Customers Platform: { lv_msg }| TYPE 'S'.
  ELSE.
    " the job ends with an error -> visible in SM37
    MESSAGE |Customers Platform error { lv_status }: { lv_msg }| TYPE 'E'.
  ENDIF.
```
