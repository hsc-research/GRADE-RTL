# Cadence Genus template for authorized environments.
# Required environment variables:
#   RTL_EVAL_LIB_SEARCH_PATH
#   RTL_EVAL_LIBRARY_FILE
#   RTL_EVAL_RTL_FILE
#   RTL_EVAL_TOP_MODULE
#   RTL_EVAL_REPORT_DIR
#
# This template contains no institution-specific paths or credentials.

set_db init_lib_search_path $::env(RTL_EVAL_LIB_SEARCH_PATH)
read_libs $::env(RTL_EVAL_LIBRARY_FILE)
read_hdl $::env(RTL_EVAL_RTL_FILE)
elaborate $::env(RTL_EVAL_TOP_MODULE)

set_db syn_generic_effort medium
set_db syn_map_effort medium
set_db syn_opt_effort medium

syn_generic
syn_map
syn_opt

file mkdir $::env(RTL_EVAL_REPORT_DIR)
redirect $::env(RTL_EVAL_REPORT_DIR)/timing.rpt { report_timing }
redirect $::env(RTL_EVAL_REPORT_DIR)/area.rpt   { report_area }
redirect $::env(RTL_EVAL_REPORT_DIR)/power.rpt  { report_power }
exit
