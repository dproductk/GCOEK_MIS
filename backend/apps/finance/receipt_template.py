"""
Static geometry for the official GCOEK fee receipt.

This is a 1:1 coordinate transcription of
``design/GCOEK_ADMISSION_CHALLAN_Borders_Fixed.pdf`` (A4 landscape,
841.89 x 595.30 pt).  Keeping the static furniture in one place makes the
renderer deterministic: the PDF is generated from vectors and embedded
Liberation Sans / Carlito fonts, not from a browser print dialog.

Coordinates are PDF points with the origin at the bottom-left.  Do not
"tidy" the values: the source form has slightly different column widths
between the three copies and the receipt is intentionally reproduced as-is.
"""

# A4 landscape, matching the source PDF's MediaBox exactly.
PAGE_SIZE = (841.89, 595.30)

# Font aliases registered by receipt_pdf.py.
FONT_REGULAR = 'LS'
FONT_BOLD = 'LSB'
FONT_URL = 'CARLITO'

# Static labels.  Sample fee rows from the source PDF are deliberately omitted
# (they are drawn from the accountant's saved fee-head snapshot at runtime).
STATIC_TEXT = [
    (46.0, 570.25, 9.3, FONT_BOLD, 'Government College of Engineering, Kolhapur'),
    (314.07, 570.25, 9.3, FONT_BOLD, 'Government College of Engineering, Kolhapur'),
    (590.94, 570.25, 9.3, FONT_BOLD, 'Government College of Engineering, Kolhapur'),
    (72.98, 558.9, 7.71, FONT_REGULAR, '(An Institute of Government of Maharashtra)'),
    (341.06, 558.9, 7.71, FONT_REGULAR, '(An Institute of Government of Maharashtra)'),
    (617.93, 558.9, 7.71, FONT_REGULAR, '(An Institute of Government of Maharashtra)'),
    (98.02, 546.83, 9.3, FONT_URL, 'https://gcoekolhapur.ac.in'),
    (366.12, 546.83, 9.3, FONT_URL, 'https://gcoekolhapur.ac.in'),
    (642.96, 546.83, 9.3, FONT_URL, 'https://gcoekolhapur.ac.in'),
    (159.36, 535.96, 7.71, FONT_REGULAR, 'Date -'),
    (421.03, 535.96, 7.71, FONT_REGULAR, 'Date -'),
    (694.21, 535.96, 7.71, FONT_REGULAR, 'Date -'),
    (52.02, 525.77, 7.71, FONT_BOLD, 'SECOND/THIRD/FOURTH YEAR ADMISSION 2026-27'),
    (320.12, 525.77, 7.71, FONT_BOLD, 'SECOND/THIRD/FOURTH YEAR ADMISSION 2026-27'),
    (596.97, 525.77, 7.71, FONT_BOLD, 'SECOND/THIRD/FOURTH YEAR ADMISSION 2026-27'),
    (98.93, 511.62, 9.3, FONT_BOLD, 'Fees Payment Challan'),
    (367.03, 511.62, 9.3, FONT_BOLD, 'Fees Payment Challan'),
    (643.88, 511.62, 9.3, FONT_BOLD, 'Fees Payment Challan'),
    (119.75, 500.27, 7.71, FONT_REGULAR, "(Cashier's Copy)"),
    (376.57, 500.27, 7.71, FONT_REGULAR, '(Student Section Copy)'),
    (664.7, 500.27, 7.71, FONT_REGULAR, "(Student's Copy)"),
    (118.14, 489.07, 7.2, FONT_BOLD, 'Challan No. ________________'),
    (378.81, 489.07, 7.2, FONT_BOLD, 'Challan No. ________________'),
    (650.96, 489.07, 7.2, FONT_BOLD, 'Challan No. ________________'),
    (118.14, 476.32, 7.2, FONT_REGULAR, 'Branch: ______________'),
    (378.81, 476.32, 7.2, FONT_REGULAR, 'Branch: ______________'),
    (650.96, 476.32, 7.2, FONT_REGULAR, 'Branch: ______________'),
    (17.78, 460.78, 7.71, FONT_REGULAR, 'Received from'),
    (287.9, 460.78, 7.71, FONT_REGULAR, 'Received from'),
    (562.73, 460.78, 7.71, FONT_REGULAR, 'Received from'),
    (17.78, 450.59, 7.71, FONT_REGULAR, 'Name : _________________________________________'),
    (287.9, 450.59, 7.71, FONT_REGULAR, 'Name : _________________________________________'),
    (562.73, 450.59, 7.71, FONT_REGULAR, 'Name : _________________________________________'),
    (17.78, 440.4, 7.71, FONT_REGULAR, 'Address : ______________________________________'),
    (287.9, 440.4, 7.71, FONT_REGULAR, 'Address : ______________________________________'),
    (562.73, 440.4, 7.71, FONT_REGULAR, 'Address : ______________________________________'),
    (17.78, 430.21, 7.71, FONT_REGULAR, '______________________________________________'),
    (287.9, 430.21, 7.71, FONT_REGULAR, '______________________________________________'),
    (562.73, 430.21, 7.71, FONT_REGULAR, '______________________________________________'),
    (17.78, 420.02, 7.71, FONT_REGULAR, 'Mobile No : ____________________, ________________'),
    (287.9, 420.02, 7.71, FONT_REGULAR, 'Mobile No : ____________________, ________________'),
    (562.73, 420.02, 7.71, FONT_REGULAR, 'Mobile No : ____________________, ________________'),
    (17.78, 409.82, 7.71, FONT_BOLD, 'Details of Fees Paid :'),
    (287.9, 409.82, 7.71, FONT_BOLD, 'Details of Fees Paid :'),
    (562.73, 409.82, 7.71, FONT_BOLD, 'Details of Fees Paid :'),
    (22.87, 395.17, 7.71, FONT_BOLD, 'Govt  Fees (in Rs.)'),
    (132.64, 395.17, 7.71, FONT_BOLD, 'Non-Govt (Other) Fees (in Rs.)'),
    (292.31, 395.17, 7.71, FONT_BOLD, 'Govt  Fees (in Rs.)'),
    (400.06, 395.17, 7.71, FONT_BOLD, 'Non-Govt (Other) Fees (in Rs.)'),
    (564.44, 395.17, 7.71, FONT_BOLD, 'Govt  Fees (in Rs.)'),
    (674.21, 395.17, 7.71, FONT_BOLD, 'Non-Govt (Other) Fees (in Rs.)'),
    (17.78, 207.24, 7.71, FONT_REGULAR, 'Total (A) >'),
    (142.4, 207.24, 7.71, FONT_REGULAR, 'Total (B)>'),
    (287.9, 207.24, 7.71, FONT_REGULAR, 'Total (A) >'),
    (407.05, 207.24, 7.71, FONT_REGULAR, 'Total (B) >'),
    (562.73, 207.24, 7.71, FONT_REGULAR, 'Total (A) >'),
    (678.86, 207.24, 7.71, FONT_REGULAR, 'Total (B) >'),
    (82.23, 190.61, 8.51, FONT_BOLD, 'TOTAL FEES PAID  (A)+(B)=>> Rs.'),
    (344.91, 190.61, 8.51, FONT_BOLD, 'TOTAL FEES PAID  (A)+(B)=>> Rs.'),
    (619.11, 190.61, 8.51, FONT_BOLD, 'TOTAL FEES PAID  (A)+(B)=>> Rs.'),
    (17.78, 174.76, 7.71, FONT_REGULAR, 'In words'),
    (287.9, 174.76, 7.71, FONT_REGULAR, 'In words'),
    (562.73, 174.76, 7.71, FONT_REGULAR, 'In words'),
    (17.78, 94.47, 7.71, FONT_REGULAR, 'Signature of                  Cashier                               Seal Of Institute'),
    (287.9, 94.47, 7.71, FONT_REGULAR, 'Signature of                  Cashier                           Seal Of Institute'),
    (562.73, 94.47, 7.71, FONT_REGULAR, 'Signature of                  Cashier                            Seal Of Institute'),
    (17.78, 85.87, 7.71, FONT_REGULAR, 'Student                       Sign'),
    (287.9, 85.87, 7.71, FONT_REGULAR, 'Student                       Sign'),
    (562.73, 85.87, 7.71, FONT_REGULAR, 'Student                       Sign'),
]

# Vector rules: (x1, y1, x2, y2, line_width).
# Page-boundary/clip artifacts from the source PDF are intentionally omitted.
LINES = [
    (16.17, 579.52, 280.41, 579.52, 1.49),
    (16.91, 580.27, 16.91, 53.8, 1.49),
    (279.67, 580.27, 279.67, 402.74, 1.49),
    (286.29, 579.52, 546.46, 579.52, 1.49),
    (287.04, 580.27, 287.04, 53.8, 1.49),
    (545.72, 580.27, 545.72, 402.74, 1.49),
    (561.11, 579.52, 825.36, 579.52, 1.49),
    (561.86, 580.27, 561.86, 53.8, 1.49),
    (824.61, 580.27, 824.61, 402.74, 1.49),
    (16.17, 403.05, 279.98, 403.05, 0.64),
    (96.4, 403.37, 96.4, 198.88, 0.64),
    (279.67, 403.37, 279.67, 386.19, 0.64),
    (286.29, 403.05, 546.03, 403.05, 0.64),
    (365.18, 403.37, 365.18, 198.88, 0.64),
    (545.72, 403.37, 545.72, 386.5, 0.64),
    (561.11, 403.05, 824.92, 403.05, 0.64),
    (634.6, 403.37, 634.6, 198.88, 0.64),
    (824.61, 403.37, 824.61, 386.5, 0.64),
    (16.17, 386.5, 279.98, 386.5, 0.64),
    (222.39, 386.81, 222.39, 182.32, 0.64),
    (279.67, 386.81, 279.67, 53.8, 1.49),
    (485.07, 386.5, 485.07, 182.32, 0.64),
    (545.72, 386.5, 545.72, 53.8, 1.49),
    (759.27, 386.5, 759.27, 182.32, 0.64),
    (824.61, 386.5, 824.61, 53.8, 1.49),
    (16.17, 215.12, 280.41, 215.12, 0.64),
    (286.29, 215.12, 546.46, 215.12, 0.64),
    (561.11, 215.12, 825.36, 215.12, 0.64),
    (16.17, 199.19, 280.41, 199.19, 0.64),
    (286.29, 199.19, 546.46, 199.19, 0.64),
    (561.11, 199.19, 825.36, 199.19, 0.64),
    (16.17, 182.64, 280.41, 182.64, 0.64),
    (286.29, 182.64, 546.46, 182.64, 0.64),
    (561.11, 182.64, 825.36, 182.64, 0.64),
    (16.17, 148.86, 280.41, 148.86, 0.64),
    (286.29, 148.86, 546.46, 148.86, 0.64),
    (561.11, 148.86, 825.36, 148.86, 0.64),
    (16.17, 54.55, 280.41, 54.55, 1.49),
    (286.29, 54.55, 546.46, 54.55, 1.49),
    (561.11, 54.55, 825.36, 54.55, 1.49),
]

# Per-copy coordinates for dynamic fields and fee tables.
# ``right``/``left`` are the outer top-rule extents from the source form.
COPIES = [
    {
        'left': 16.17,
        'right': 280.41,
        'govt_end': 96.4,
        'name_divider': 222.39,
        'challan_x': 118.14,
        'branch_x': 118.14,
        'name_x': 17.78,
        'address_x': 17.78,
        'mobile_x': 17.78,
        'date_x': 159.36,
        'govt_name_x': 17.78,
        'govt_amount_right': 95.4,
        'serial_x': 104.7,
        'nongovt_name_x': 118.1,
        'nongovt_amount_right': 278.71,
        'total_b_label_x': 142.4,
        'grand_total_x': 82.23,
        'in_words_x': 17.78,
    },
    {
        'left': 286.29,
        'right': 546.46,
        'govt_end': 365.18,
        'name_divider': 485.07,
        'challan_x': 378.81,
        'branch_x': 378.81,
        'name_x': 287.9,
        'address_x': 287.9,
        'mobile_x': 287.9,
        'date_x': 421.03,
        'govt_name_x': 287.9,
        'govt_amount_right': 364.18,
        'serial_x': 369.4,
        'nongovt_name_x': 378.8,
        'nongovt_amount_right': 544.76,
        'total_b_label_x': 407.05,
        'grand_total_x': 344.91,
        'in_words_x': 287.9,
    },
    {
        'left': 561.11,
        'right': 825.36,
        'govt_end': 634.6,
        'name_divider': 759.27,
        'challan_x': 650.96,
        'branch_x': 650.96,
        'name_x': 562.73,
        'address_x': 562.73,
        'mobile_x': 562.73,
        'date_x': 694.21,
        'govt_name_x': 562.73,
        'govt_amount_right': 633.6,
        'serial_x': 640.2,
        'nongovt_name_x': 651.0,
        'nongovt_amount_right': 823.66,
        'total_b_label_x': 678.86,
        'grand_total_x': 619.11,
        'in_words_x': 562.73,
    },
]

# Three extra underscores (13 -> 16) so a receipt number set at the larger
# bold challan size fits its blank without auto-shrink.
CHALLAN_LABEL = 'Challan No. ________________'
BRANCH_LABEL = 'Branch: ______________'
NAME_LABEL = 'Name : _________________________________________'
ADDRESS_LABEL = 'Address : ______________________________________'
ADDRESS_LINE_2 = '______________________________________________'
MOBILE_LABEL = 'Mobile No : ____________________, ________________'
DATE_LABEL = 'Date -'
TOTAL_LABEL = 'TOTAL FEES PAID  (A)+(B)=>> Rs.'
IN_WORDS_LABEL = 'In words'

# Fixed baselines from the source table.  Row 0 is taller in the original
# because the sample tuition/gymkhana descriptions wrap to multiple lines.
FEE_ROW_Y = [378.6, 337.8, 323.8, 310.4, 296.4, 284.3, 269.7, 259.5, 244.8, 234.6]
FEE_FIRST_ROW_EXTRA_Y = [370.0, 361.4]
FEE_TABLE_BOTTOM = 219.0
