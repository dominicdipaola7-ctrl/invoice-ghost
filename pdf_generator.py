from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_LEFT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import io

INK = colors.HexColor('#0D0D0D')
GHOST = colors.HexColor('#6B6B6B')
PALE = colors.HexColor('#F5F4F0')
ACCENT = colors.HexColor('#1A1A2E')
LINE = colors.HexColor('#E0DED8')
WHITE = colors.white

def build_style(name, font='Helvetica', size=10, color=INK, align=TA_LEFT, bold=False):
    return ParagraphStyle(name=name, fontName='Helvetica-Bold' if bold else font,
                          fontSize=size, textColor=color, alignment=align,
                          leading=size * 1.4, spaceAfter=0)

def generate_pdf(data: dict, brand_color: str = "#1A1A2E") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                            topMargin=18*mm, bottomMargin=18*mm)
    accent = colors.HexColor(brand_color)
    story = []

    h1 = build_style('h1', size=28, bold=True, color=accent)
    h2 = build_style('h2', size=11, bold=True, color=INK)
    body = build_style('body', size=9, color=INK)
    small = build_style('small', size=8, color=GHOST)
    small_r = build_style('small_r', size=8, color=GHOST, align=TA_RIGHT)
    body_r = build_style('body_r', size=9, color=INK, align=TA_RIGHT)
    bold_r = build_style('bold_r', size=10, bold=True, color=INK, align=TA_RIGHT)
    total_s = build_style('total_s', size=13, bold=True, color=WHITE, align=TA_RIGHT)

    header_data = [[
        Paragraph("INVOICE", h1),
        Table([
            [Paragraph("Invoice No.", small_r), Paragraph(data.get('invoice_number','INV-001'), body_r)],
            [Paragraph("Date", small_r), Paragraph(data.get('invoice_date',''), body_r)],
            [Paragraph("Due", small_r), Paragraph(data.get('due_date',''), body_r)],
        ], colWidths=[25*mm, 45*mm])
    ]]
    header_tbl = Table(header_data, colWidths=[105*mm, 70*mm])
    header_tbl.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('ALIGN',(1,0),(1,0),'RIGHT')]))
    story.append(header_tbl)
    story.append(HRFlowable(width="100%", thickness=1, color=accent, spaceAfter=6*mm, spaceBefore=4*mm))

    from_col = [Paragraph("FROM", small), Spacer(1,2*mm),
                Paragraph(data.get('freelancer_name',''), h2),
                Paragraph(data.get('freelancer_email',''), small)]
    to_col = [Paragraph("BILL TO", small), Spacer(1,2*mm),
              Paragraph(data.get('client_name',''), h2),
              Paragraph(data.get('client_email',''), small)]
    parties = Table([[from_col, to_col]], colWidths=[87*mm, 87*mm])
    parties.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP')]))
    story.append(parties)
    story.append(Spacer(1, 8*mm))

    col_w = [88*mm, 18*mm, 18*mm, 25*mm, 27*mm]
    tbl_header = ['Description', 'Qty', 'Unit', 'Rate', 'Amount']
    rows = [[Paragraph(h, build_style(f'th{i}', size=8, bold=True, color=WHITE,
              align=TA_RIGHT if i > 0 else TA_LEFT)) for i, h in enumerate(tbl_header)]]

    items = data.get('line_items', [])
    for i, item in enumerate(items):
        bg = PALE if i % 2 == 0 else WHITE
        cur = data.get('currency','USD')
        sym = '$' if cur == 'USD' else cur + ' '
        row = [
            Paragraph(item.get('description',''), body),
            Paragraph(str(item.get('quantity',1)), body_r),
            Paragraph(item.get('unit',''), build_style('u',size=9,color=GHOST,align=TA_RIGHT)),
            Paragraph(f"{sym}{item.get('rate',0):,.2f}", body_r),
            Paragraph(f"{sym}{item.get('amount',0):,.2f}", body_r),
        ]
        rows.append(row)

    items_tbl = Table(rows, colWidths=col_w, repeatRows=1)
    items_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), accent),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [PALE, WHITE]),
        ('GRID', (0,0), (-1,-1), 0.3, LINE),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 5), ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (0,-1), 4), ('RIGHTPADDING', (-1,0), (-1,-1), 4),
    ]))
    story.append(items_tbl)
    story.append(Spacer(1, 4*mm))

    sym = '$' if data.get('currency','USD') == 'USD' else data.get('currency','') + ' '
    subtotal = data.get('subtotal', 0)
    tax = data.get('tax_amount', 0)
    total = data.get('total', 0)
    tax_rate = data.get('tax_rate', 0)

    summary_rows = [
        [Paragraph('Subtotal', small_r), Paragraph(f"{sym}{subtotal:,.2f}", body_r)],
    ]
    if tax > 0:
        summary_rows.append([Paragraph(f'Tax ({tax_rate}%)', small_r), Paragraph(f"{sym}{tax:,.2f}", body_r)])

    summary_tbl = Table(summary_rows, colWidths=[140*mm, 30*mm])
    summary_tbl.setStyle(TableStyle([('ALIGN',(0,0),(-1,-1),'RIGHT'), ('TOPPADDING',(0,0),(-1,-1),2)]))
    story.append(summary_tbl)
    story.append(Spacer(1, 2*mm))

    total_row = Table([[Paragraph(f"TOTAL DUE  {sym}{total:,.2f}", total_s)]],
                      colWidths=[174*mm])
    total_row.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1), accent),
        ('ALIGN',(0,0),(-1,-1),'RIGHT'),
        ('TOPPADDING',(0,0),(-1,-1),8), ('BOTTOMPADDING',(0,0),(-1,-1),8),
        ('RIGHTPADDING',(0,0),(-1,-1),6),
    ]))
    story.append(total_row)

    if data.get('notes'):
        story.append(Spacer(1, 8*mm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=LINE))
        story.append(Spacer(1, 3*mm))
        story.append(Paragraph(data['notes'], small))

    story.append(Spacer(1, 8*mm))
    story.append(Paragraph("Generated with Invoice Ghost · invoiceghost.com",
                            build_style('footer', size=7, color=LINE, align=TA_CENTER)))

    doc.build(story)
    return buf.getvalue()
