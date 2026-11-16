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
