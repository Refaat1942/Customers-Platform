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
