"""
Admission Verification Form PDF Generator and Data Provider.

Produces the official:
'Government College Of Engineering, Kolhapur
Application Form for Admission to Second/Third/Fourth Year Degree Course'

Includes:
- 18 standardized fields matching the physical institutional application form
- Digital verification endorsements by Class Teacher and HOD with authoritative timestamps
- Student declaration section
- 'For Office Use Only' cashier and clerk clearance section
"""
import io
from decimal import Decimal
from django.utils import timezone
from django.db.models import Sum

# NOTE: reportlab is imported lazily inside generate_admission_verification_pdf.
# The JSON data provider below must stay import-safe so the admission-form-data
# API never 500s just because the optional PDF render library is missing.

from apps.authentication.models import RoleAssignment
from apps.results.models import EligibilityVerification, SemesterResult
from apps.results.serializers import _staff_display_name
from apps.finance.models import PaymentLedger, StudentFeeAssessment


def get_student_admission_form_data(student, eligibility=None):
    """
    Assembles authoritative dictionary of all fields required for the
    Admission Application Form and Accountant Clearance proof.
    """
    if eligibility is None:
        qs = student.eligibility_records.select_related(
            'academic_year',
            'target_semester',
            'department',
            'class_teacher',
            'class_teacher__faculty_profile',
            'hod',
            'hod__faculty_profile',
        )
        eligibility = qs.filter(final_eligible=True).order_by('-created_at').first() or qs.order_by('-created_at').first()

    enr = (
        student.enrollments.filter(is_current=True)
        .select_related('department', 'semester', 'division', 'division__class_teacher', 'academic_year')
        .first()
    )

    academic_year_code = (
        getattr(getattr(eligibility, 'academic_year', None), 'code', None)
        or getattr(getattr(enr, 'academic_year', None), 'code', None)
        or '—'
    )

    target_sem_num = (
        getattr(getattr(eligibility, 'target_semester', None), 'number', None)
        or ((enr.semester.number + 1) if (enr and enr.semester) else None)
    )

    if target_sem_num in (3, 4):
        target_year_str = 'Second Year'
    elif target_sem_num in (5, 6):
        target_year_str = 'Third Year'
    elif target_sem_num in (7, 8):
        target_year_str = 'Fourth Year'
    else:
        target_year_str = 'Second/Third/Fourth Year'

    # Personal details
    pd = getattr(student, 'personal_details', None)
    adm = student.admissions.select_related('source_import_row').first()
    raw_adm = (
        getattr(getattr(adm, 'source_import_row', None), 'raw_data', {})
        if adm
        else {}
    )

    # 1. Full Name
    full_name = student.display_name or f"{student.last_name} {student.first_name} {student.middle_name}".strip()

    # 2. PRN Number
    prn_number = student.enrollment_no or student.application_id or '—'

    # 3. Branch
    branch = (
        getattr(getattr(enr, 'department', None), 'name', None)
        or getattr(getattr(eligibility, 'department', None), 'name', None)
        or '—'
    )

    # 4. Caste
    caste = getattr(pd, 'caste', '') or raw_adm.get('caste') or raw_adm.get('cast') or raw_adm.get('sub caste') or '—'

    # 5. Category (never default to OPEN: it is a legal reservation claim)
    category = getattr(adm, 'category', '') or raw_adm.get('category') or ''

    # 6. Gender
    gender = getattr(pd, 'gender', '')
    if gender:
        gender = gender.capitalize()
    else:
        gender = '—'

    # 7. Religion
    religion = getattr(pd, 'religion', '') or raw_adm.get('religion') or '—'

    # 8. Physically disabled
    is_pwd = 'Yes' if ('PWD' in category.upper() or 'PH' in category.upper() or str(raw_adm.get('ph') or '').lower() in ('yes', 'true', 'y')) else 'No'

    # 9. Student Mobile
    mobile_student = getattr(pd, 'student_mobile', '') or getattr(student.user, 'phone_number', '') or '—'

    # 10. Parent Mobile
    guardian = student.guardians.filter(relationship='FATHER').first() or student.guardians.first()
    mobile_parent = getattr(guardian, 'mobile', '') or '—'

    # 11. ABC ID
    abc_id = getattr(pd, 'abc_id', '') or raw_adm.get('abc_id') or '—'

    # 12 & 13. Addresses
    addr_corr = student.addresses.filter(address_type='CORRESPONDENCE').first()
    addr_perm = student.addresses.filter(address_type='PERMANENT').first()
    if not addr_corr:
        addr_corr = addr_perm
    if not addr_perm:
        addr_perm = addr_corr

    def _fmt_addr(a):
        if not a:
            return '—'
        parts = [
            a.address_line_1,
            a.address_line_2,
            a.village,
            a.taluka,
            a.district,
            a.state,
        ]
        text = ', '.join([p.strip() for p in parts if p and p.strip()])
        if a.pincode:
            text += f' - {a.pincode}'
        return text or '—'

    local_address = _fmt_addr(addr_corr)
    permanent_address = _fmt_addr(addr_perm)

    # 14. Income Certificate Number
    inc_doc = student.documents.filter(document_type='INCOME_CERTIFICATE').first()
    income_cert_no = getattr(inc_doc, 'title', '') if inc_doc else raw_adm.get('income_cert_no') or '—'

    # 15. Parent Annual Income
    income_val = getattr(guardian, 'annual_income', None) or raw_adm.get('annual_income')
    if income_val:
        try:
            parent_annual_income = f"₹{int(float(income_val)):,}"
        except Exception:
            parent_annual_income = str(income_val)
    else:
        parent_annual_income = '—'

    # 16. Non-Creamy Layer Certificate
    has_ncl = 'Yes' if (category.upper() in ['OBC', 'VJ', 'NT-1', 'NT-2', 'NT-3', 'SBC', 'SEBC']) else 'N/A'

    # 17. First Year fee receipt & date
    fy_ledger = (
        PaymentLedger.objects.filter(student=student)
        .order_by('payment_date')
        .first()
    )
    if fy_ledger:
        fy_receipt_info = f"Receipt No: {fy_ledger.receipt_no}, Date: {fy_ledger.payment_date.strftime('%d/%m/%Y')}"
    else:
        fy_receipt_info = '—'

    # 18. Credits Earned
    sem_results = student.semester_results.all()
    fy_credits = sum(r.total_credits_earned for r in sem_results if r.semester.number in (1, 2))
    sy_credits = sum(r.total_credits_earned for r in sem_results if r.semester.number in (3, 4))
    tot_credits = sum(r.total_credits_earned for r in sem_results)
    if eligibility and eligibility.total_credits_earned > tot_credits:
        tot_credits = eligibility.total_credits_earned

    # Class Teacher Approval Resolution
    ct_status = getattr(eligibility, 'class_teacher_status', 'PENDING') if eligibility else 'PENDING'
    ct_name = _staff_display_name(getattr(eligibility, 'class_teacher', None)) if eligibility else ''
    if not ct_name and enr and enr.division and enr.division.class_teacher:
        ct_name = _staff_display_name(enr.division.class_teacher)
    if not ct_name and enr:
        ra_ct = RoleAssignment.objects.filter(
            role__name__icontains='Class Teacher',
            department_id=enr.department_id,
            status='ACTIVE',
        ).first()
        if ra_ct:
            ct_name = _staff_display_name(ra_ct.user)
    if not ct_name:
        ct_name = 'Class Teacher'

    ct_time = getattr(eligibility, 'class_teacher_reviewed_at', None) if eligibility else None
    ct_time_str = ct_time.strftime('%d-%b-%Y %I:%M %p IST') if ct_time else ('Pending' if eligibility else '—')

    # HOD Approval Resolution
    hod_status = getattr(eligibility, 'hod_status', 'PENDING') if eligibility else 'PENDING'
    hod_name = _staff_display_name(getattr(eligibility, 'hod', None)) if eligibility else ''
    if not hod_name and enr:
        ra_hod = RoleAssignment.objects.filter(
            role__name__icontains='Head of Department',
            department_id=enr.department_id,
            status='ACTIVE',
        ).first()
        if ra_hod:
            hod_name = _staff_display_name(ra_hod.user)
    if not hod_name:
        hod_name = 'Head of Department'

    hod_time = getattr(eligibility, 'hod_reviewed_at', None) if eligibility else None
    hod_time_str = hod_time.strftime('%d-%b-%Y %I:%M %p IST') if hod_time else ('Pending' if eligibility else '—')

    final_eligible = bool(eligibility and eligibility.final_eligible)
    has_verification = eligibility is not None

    # Compute explicit verification stage for tracking
    if not has_verification:
        verification_stage = 'NOT_STARTED'
        verification_stage_label = 'Verification Not Started'
        verification_stage_tone = 'gray'
        can_download = False
    elif final_eligible:
        verification_stage = 'ELIGIBLE'
        verification_stage_label = 'Verified by CT & HOD'
        verification_stage_tone = 'green'
        can_download = True
    elif hod_status == 'FLAGGED' or ct_status == 'FLAGGED':
        verification_stage = 'FLAGGED'
        verification_stage_label = 'Flagged for Clarification'
        verification_stage_tone = 'amber'
        can_download = False
    elif hod_status == 'REJECTED' or ct_status == 'REJECTED':
        verification_stage = 'REJECTED'
        verification_stage_label = 'Not Eligible'
        verification_stage_tone = 'red'
        can_download = False
    elif ct_status == 'APPROVED' and hod_status == 'PENDING':
        verification_stage = 'HOD_PENDING'
        verification_stage_label = 'Awaiting HOD Endorsement'
        verification_stage_tone = 'amber'
        can_download = False
    elif ct_status == 'PENDING':
        verification_stage = 'TEACHER_PENDING'
        verification_stage_label = 'Class Teacher Review Pending'
        verification_stage_tone = 'amber'
        can_download = False
    else:
        verification_stage = 'PENDING'
        verification_stage_label = 'Pending Verification'
        verification_stage_tone = 'amber'
        can_download = False

    remarks = (
        (getattr(eligibility, 'hod_remarks', '') or getattr(eligibility, 'class_teacher_remarks', ''))
        if eligibility
        else ''
    )

    # Fee Assessment / Due for Office Use
    assessment = StudentFeeAssessment.objects.filter(student=student).order_by('-created_at').first()
    fee_amount_str = f"₹{assessment.total_fee:,.2f}" if assessment else '₹ —'

    latest_payment = PaymentLedger.objects.filter(student=student).order_by('-payment_date').first()

    return {
        'student_id': str(student.id),
        'academic_year_code': academic_year_code,
        'target_year_str': target_year_str,
        'form_title': f'Application Form for Admission to {target_year_str} Degree Course',
        'full_name': full_name,
        'prn_number': prn_number,
        'branch': branch,
        'caste': caste,
        'category': category,
        'gender': gender,
        'religion': religion,
        'physically_disabled': is_pwd,
        'mobile_student': mobile_student,
        'mobile_parent': mobile_parent,
        'abc_id': abc_id,
        'local_address': local_address,
        'permanent_address': permanent_address,
        'income_cert_no': income_cert_no,
        'parent_annual_income': parent_annual_income,
        'non_creamy_layer': has_ncl,
        'fy_receipt_info': fy_receipt_info,
        'credits_first_year': str(fy_credits),
        'credits_second_year': str(sy_credits) if target_sem_num > 4 else '—',
        'total_credits': str(tot_credits),
        'has_verification': has_verification,
        'final_eligible': final_eligible,
        'verification_stage': verification_stage,
        'verification_stage_label': verification_stage_label,
        'verification_stage_tone': verification_stage_tone,
        'can_download': can_download,
        'remarks': remarks,
        'class_teacher_verification': {
            'status': ct_status,
            'is_approved': ct_status == 'APPROVED',
            'name': ct_name,
            'timestamp': ct_time_str,
            'remarks': getattr(eligibility, 'class_teacher_remarks', '') if eligibility else '',
        },
        'hod_verification': {
            'status': hod_status,
            'is_approved': hod_status == 'APPROVED',
            'name': hod_name,
            'timestamp': hod_time_str,
            'remarks': getattr(eligibility, 'hod_remarks', '') if eligibility else '',
        },
        'office_use': {
            'eligible_for_admission': 'Yes' if final_eligible else 'Pending Verification',
            'admission_fee_amount': fee_amount_str,
            'receipt_number': latest_payment.receipt_no if latest_payment else '—',
            'utr_no': latest_payment.transaction_ref if (latest_payment and latest_payment.transaction_ref) else '—',
        },
    }


def generate_admission_verification_pdf(data):
    """
    Renders an official single-page A4 PDF reproduction of the physical admission form,
    complete with stamps, timestamps, photo holder, and accountant cashier section.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            KeepTogether,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError(
            'PDF generation requires the reportlab package. '
            'Install it (pip install reportlab) and retry.'
        ) from exc
    buf = io.BytesIO()

    # Exact A4 page with 24pt margins to comfortably fit entire form on 1 sheet
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=28,
        rightMargin=28,
        topMargin=22,
        bottomMargin=20,
    )

    styles = getSampleStyleSheet()

    # Custom crisp typography styles
    style_inst_title = ParagraphStyle(
        'InstTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=14,
        alignment=1,  # Centered
        textColor=colors.HexColor('#0f172a'),
    )

    style_sub_title = ParagraphStyle(
        'SubTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=12,
        alignment=1,
        textColor=colors.HexColor('#1e293b'),
    )

    style_acad_year = ParagraphStyle(
        'AcadYear',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=10,
        alignment=0,  # Left
        textColor=colors.HexColor('#0f172a'),
    )

    style_field_label = ParagraphStyle(
        'FieldLabel',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.8,
        leading=9.5,
        textColor=colors.HexColor('#1e293b'),
    )

    style_field_val = ParagraphStyle(
        'FieldVal',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=9.5,
        textColor=colors.HexColor('#090d16'),
    )

    style_stamp_title = ParagraphStyle(
        'StampTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9,
        alignment=1,
        textColor=colors.HexColor('#166534'),
    )

    style_stamp_sub = ParagraphStyle(
        'StampSub',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=6.5,
        leading=8,
        alignment=1,
        textColor=colors.HexColor('#1e293b'),
    )

    style_office_header = ParagraphStyle(
        'OfficeHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#0f172a'),
    )

    story = []

    # 1. Header Box Table: Left = College Titles & Academic Year; Right = Photo Box
    photo_box = Table(
        [
            [Paragraph("<font size=6.5 color='#64748b'>Affix Passport<br/>Size Photograph<br/>Here</font>", ParagraphStyle('Ph', alignment=1, leading=8))]
        ],
        colWidths=[76],
        rowHeights=[78],
    )
    photo_box.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#475569')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    header_text_cells = [
        [Paragraph("Government College Of Engineering, Kolhapur", style_inst_title)],
        [Spacer(1, 2)],
        [Paragraph(data['form_title'], style_sub_title)],
        [Spacer(1, 4)],
        [Paragraph(f"<b>Academic Year {data['academic_year_code']}</b>", style_acad_year)],
    ]
    header_left = Table(header_text_cells, colWidths=[450])
    header_left.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
    ]))

    header_table = Table([[header_left, photo_box]], colWidths=[455, 84])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 4))

    # Helper function to generate field rows
    def field_row(num_label, custom_right=None):
        p_label = Paragraph(f"<b>{num_label}</b>", style_field_label)
        p_val = custom_right if custom_right else Paragraph("", style_field_val)
        return [p_label, p_val]

    # Clean prefilled values (PRN, full name, branch, caste, gender)
    val_name = data.get('full_name', '') if data.get('full_name') != '—' else ''
    val_prn = data.get('prn_number', '') if data.get('prn_number') != '—' else ''
    val_branch = data.get('branch', '') if data.get('branch') != '—' else ''
    val_caste = data.get('caste', '') if data.get('caste') != '—' else ''
    val_gender = data.get('gender', '') if data.get('gender') != '—' else ''

    # Item 6 & 7: prefilled gender and blank handwriting line for religion
    gender_religion_right = Paragraph(
        f"<b>{val_gender}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <b>7. Religion :</b> _________________",
        style_field_label
    )

    # Item 18 with 1st, 2nd, 3rd year and Total credits blanks
    credits_row_right = Paragraph(
        "__________ &nbsp;&nbsp;&nbsp;&nbsp; <b>Second Year:</b> __________ &nbsp;&nbsp;&nbsp;&nbsp; <b>Third Year:</b> __________ &nbsp;&nbsp;&nbsp;&nbsp; <b>Total:</b> __________",
        style_field_label
    )

    # 18 Items Data Table with prefilled basic identity and generous space for remaining manual handwriting
    items_table_data = [
        field_row("1. Full Name of Student:", Paragraph(val_name, style_field_val)),
        field_row("2. PRN Number :", Paragraph(val_prn, style_field_val)),
        field_row("3. Branch :", Paragraph(val_branch, style_field_val)),
        field_row("4. Caste:", Paragraph(val_caste, style_field_val)),
        field_row("5. Category (Open/SC/ST/OBC/VJ/NT-1/NT-2/NT-3/SEBC/EWS/TFWS):"),
        field_row("6. Gender (Male/ Female/Other):", gender_religion_right),
        field_row("8. Whether Student is Physically Disabled (Yes/No):"),
        field_row("9. Mobile Number of Student:"),
        field_row("10. Mobile Number of Parent:"),
        field_row("11. ABC ID of Student:"),
        field_row("12. Local Address:"),
        field_row(""),  # Second line for address handwriting
        field_row("13. Permanent Address:"),
        field_row(""),  # Second line for permanent address handwriting
        field_row("14. Income Certificate Number:"),
        field_row("15. Parent's Annual Income:"),
        field_row("16. Whether Student has Non-Creamy Layer Certificate (Yes/No):"),
        field_row("17. First Year admission Fees Receipt Number And Date:"),
        field_row(
            "18. Total Credits Earned in First Year:",
            credits_row_right
        ),
    ]

    form_table = Table(items_table_data, colWidths=[240, 299])
    form_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2.8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.8),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('LINEBELOW', (1, 0), (1, -1), 0.5, colors.HexColor('#64748b')),
    ]))
    story.append(form_table)
    story.append(Spacer(1, 5))

    # Student Signatures row with prefilled name
    student_sig_table = Table([
        [
            Paragraph("<b>Signature of Student:</b> ___________________________", style_field_label),
            Paragraph(f"<b>Full Name of Student:</b> <b>{val_name}</b>", style_field_label),
        ]
    ], colWidths=[260, 279])
    student_sig_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(student_sig_table)
    story.append(Spacer(1, 4))

    # Class Teacher & HOD Approval Seals / Stamping Box (Confirming Eligibility)
    ct_info = data['class_teacher_verification']
    hod_info = data['hod_verification']

    def _make_seal(role_title, is_approved, person_name, timestamp_str):
        if is_approved:
            status_text = "✔ APPROVED & ENDORSED"
            border_color = colors.HexColor('#16a34a')
            bg_color = colors.HexColor('#f0fdf4')
            text_color = "#166534"
        else:
            status_text = "⏳ PENDING VERIFICATION"
            border_color = colors.HexColor('#d97706')
            bg_color = colors.HexColor('#fffbeb')
            text_color = "#92400e"

        seal_content = [
            [Paragraph(f"<b>{role_title}</b>", style_field_label)],
            [Paragraph(f"<font color='{text_color}'><b>{status_text}</b></font>", style_stamp_title)],
            [Paragraph(f"<b>{person_name}</b>", style_stamp_sub)],
            [Paragraph(f"Timestamp: {timestamp_str}", style_stamp_sub)],
        ]
        t = Table(seal_content, colWidths=[255])
        t.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.75, border_color),
            ('BACKGROUND', (0, 0), (-1, -1), bg_color),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 1.8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1.8),
        ]))
        return t

    ct_seal = _make_seal("Signature of Class Teacher", ct_info['is_approved'], ct_info['name'], ct_info['timestamp'])
    hod_seal = _make_seal("Signature of HOD", hod_info['is_approved'], hod_info['name'], hod_info['timestamp'])

    seals_table = Table([[ct_seal, hod_seal]], colWidths=[265, 274])
    seals_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(seals_table)
    story.append(Spacer(1, 6))

    # For Office Use Only Section (Matching blank physical form)
    is_eligible = bool(data.get('final_eligible'))
    eligibility_val_html = "<font color='#166534'><b>Yes</b></font>" if is_eligible else "<font color='#dc2626'><b>No</b></font>"

    office_data = [
        [
            Paragraph("<b><u>For Office Use Only:</u></b>", style_office_header),
            "",
        ],
        [
            Paragraph(f"1. <b>Eligible for Admission:</b> {eligibility_val_html}", style_field_label),
            Paragraph("2. <b>Admission Fee Amount:</b> ___________________________", style_field_label),
        ],
        [
            Paragraph("(Signature of Student Section Clerk) ___________________________", style_field_label),
            "",
        ],
        [
            Paragraph("3. <b>Admission Fee Receipt Number:</b> ___________________________", style_field_label),
            Paragraph("4. <b>UTR No:</b> ___________________________", style_field_label),
        ],
        [
            "",
            Paragraph("(Signature of Cashier) ___________________________", style_field_label),
        ]
    ]

    office_table = Table(office_data, colWidths=[270, 269])
    office_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#64748b')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('TOPPADDING', (0, 0), (-1, -1), 2.2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.2),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('SPAN', (0, 0), (1, 0)),
        ('SPAN', (0, 2), (1, 2)),
    ]))
    story.append(office_table)

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()
