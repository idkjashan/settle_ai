"""
app/domain/settlement_escalation/pdf_service.py
High-fidelity ReportLab PDF document generator for Settlement Certificates and Adjuster Review Dossiers.
"""
from io import BytesIO
import logging
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from app.domain.settlement_escalation.exceptions import PDFGenerationError
from app.domain.settlement_escalation.schemas import (
    HumanAdjusterDossierDTO,
    SettlementVoucherDTO,
)

logger = logging.getLogger(__name__)


class ReportLabPDFService:
    """
    Renders professional, printable PDF documents in memory using ReportLab.
    """

    def generate_settlement_voucher_pdf(self, voucher: SettlementVoucherDTO) -> bytes:
        """
        Renders an official, legally auditable PDF Settlement Certificate.
        """
        buffer = BytesIO()
        try:
            doc = SimpleDocTemplate(
                buffer,
                pagesize=letter,
                rightMargin=36,
                leftMargin=36,
                topMargin=36,
                bottomMargin=36,
            )

            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                "DocTitle",
                parent=styles["Heading1"],
                fontName="Helvetica-Bold",
                fontSize=18,
                leading=22,
                textColor=colors.HexColor("#1A365D"),
                alignment=1,  # Center
            )
            subtitle_style = ParagraphStyle(
                "DocSubtitle",
                parent=styles["Normal"],
                fontName="Helvetica",
                fontSize=10,
                leading=14,
                textColor=colors.HexColor("#4A5568"),
                alignment=1,
            )
            section_heading = ParagraphStyle(
                "SectionHead",
                parent=styles["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=12,
                leading=16,
                textColor=colors.HexColor("#2B6CB0"),
                spaceAfter=6,
            )
            cell_bold = ParagraphStyle(
                "CellBold",
                parent=styles["Normal"],
                fontName="Helvetica-Bold",
                fontSize=9,
                leading=12,
                textColor=colors.HexColor("#2D3748"),
            )
            cell_normal = ParagraphStyle(
                "CellNormal",
                parent=styles["Normal"],
                fontName="Helvetica",
                fontSize=9,
                leading=12,
                textColor=colors.HexColor("#4A5568"),
            )
            fineprint_style = ParagraphStyle(
                "Fineprint",
                parent=styles["Normal"],
                fontName="Helvetica-Oblique",
                fontSize=7.5,
                leading=10,
                textColor=colors.HexColor("#718096"),
            )

            story = []

            # 1. Header
            story.append(Paragraph("AUTO-SETTLE AI — OFFICIAL SETTLEMENT CERTIFICATE", title_style))
            story.append(Paragraph("Autonomous Video-to-Cash Claims Adjuster • IRDAI Statutory Motor Tariff Compliance", subtitle_style))
            story.append(Spacer(1, 15))

            # 2. Metadata Table
            meta_data = [
                [Paragraph("Voucher ID:", cell_bold), Paragraph(voucher.voucher_id, cell_normal),
                 Paragraph("Issue Date:", cell_bold), Paragraph(voucher.issued_at.strftime("%d %b %Y %H:%M UTC"), cell_normal)],
                [Paragraph("Claim ID:", cell_bold), Paragraph(str(voucher.claim_id), cell_normal),
                 Paragraph("Policy ID:", cell_bold), Paragraph(voucher.policy_id, cell_normal)],
                [Paragraph("Registration No:", cell_bold), Paragraph(voucher.registration_number, cell_normal),
                 Paragraph("Vehicle:", cell_bold), Paragraph(voucher.vehicle_make_model, cell_normal)],
            ]
            meta_table = Table(meta_data, colWidths=[95, 175, 85, 185])
            meta_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7FAFC")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("PADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            story.append(meta_table)
            story.append(Spacer(1, 15))

            # 3. Settlement Amount Banner
            amt_data = [
                [Paragraph("TOTAL APPROVED CASH-IN-LIEU SETTLEMENT:", cell_bold),
                 Paragraph(f"<b>₹{voucher.settled_amount_inr:,.2f}</b>", ParagraphStyle("BigAmt", parent=cell_bold, fontSize=14, leading=16, textColor=colors.HexColor("#22543D")))],
                [Paragraph("Amount in Words:", cell_bold), Paragraph(f"<i>{voucher.settled_amount_words}</i>", cell_normal)],
                [Paragraph("Disbursement Channel:", cell_bold), Paragraph(f"IMPS / UPI Reference: {voucher.disbursement_ref}", cell_normal)],
            ]
            if voucher.beneficiary_upi_id:
                amt_data.append([Paragraph("Beneficiary UPI ID:", cell_bold), Paragraph(voucher.beneficiary_upi_id, cell_normal)])

            amt_table = Table(amt_data, colWidths=[180, 360])
            amt_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EDFDFD")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#B2F5EA")),
                ("PADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            story.append(amt_table)
            story.append(Spacer(1, 15))

            # 4. Itemized Damaged Parts Table
            story.append(Paragraph("Apportioned Damaged Components (Committed to Unrepaired Claims Ledger):", section_heading))
            part_rows = [
                [Paragraph("Part Name / Key", cell_bold), Paragraph("Damage Grade", cell_bold), Paragraph("Gross Line Item", cell_bold), Paragraph("Apportioned Cash Payout", cell_bold)]
            ]
            for p in voucher.apportioned_parts:
                part_rows.append([
                    Paragraph(f"<b>{p.display_part_name}</b><br/><code>{p.canonical_part_key}</code>", cell_normal),
                    Paragraph(p.damage_class, cell_normal),
                    Paragraph(f"₹{p.gross_line_item_inr:,.2f}", cell_normal),
                    Paragraph(f"<b>₹{p.apportioned_amount_inr:,.2f}</b>", cell_bold),
                ])
            parts_table = Table(part_rows, colWidths=[180, 110, 120, 130])
            parts_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
                ("PADDING", (0, 0), (-1, -1), 5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            story.append(parts_table)
            story.append(Spacer(1, 15))

            # 5. Legal Notice & Digital Seal
            notice_text = (
                "<b>STATUTORY UNREPAIRED DAMAGE NOTICE (IRDAI / IMT RULES):</b><br/>"
                "By accepting cash-in-lieu settlement, the insured agrees that the components listed above have been compensated without physical repair verification. "
                "These parts have been permanently recorded in the National Insurer Unrepaired Claims Ledger. Future claims on these exact components will be excluded "
                "unless prior physical restoration is proven by an authorized surveyor inspection. This document is electronically generated and digitally signed."
            )
            story.append(Paragraph(notice_text, fineprint_style))
            story.append(Spacer(1, 8))

            seal_text = f"<b>SHA-256 DIGITAL INTEGRITY SEAL:</b> <code>{voucher.digital_signature_sha256}</code>"
            story.append(Paragraph(seal_text, fineprint_style))

            doc.build(story)
            pdf_bytes = buffer.getvalue()
            buffer.close()
            return pdf_bytes

        except Exception as e:
            logger.error(f"Failed to generate settlement voucher PDF: {e}", exc_info=True)
            raise PDFGenerationError(f"PDF settlement voucher generation failed: {e}")

    def generate_adjuster_dossier_pdf(self, dossier: HumanAdjusterDossierDTO) -> bytes:
        """
        Renders a comprehensive Claims Adjuster Investigation Dossier.
        """
        buffer = BytesIO()
        try:
            doc = SimpleDocTemplate(
                buffer,
                pagesize=letter,
                rightMargin=36,
                leftMargin=36,
                topMargin=36,
                bottomMargin=36,
            )

            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                "DocTitle",
                parent=styles["Heading1"],
                fontName="Helvetica-Bold",
                fontSize=16,
                leading=20,
                textColor=colors.HexColor("#742A2A"),
                alignment=1,
            )
            subtitle_style = ParagraphStyle(
                "DocSubtitle",
                parent=styles["Normal"],
                fontName="Helvetica",
                fontSize=9.5,
                leading=13,
                textColor=colors.HexColor("#4A5568"),
                alignment=1,
            )
            section_heading = ParagraphStyle(
                "SectionHead",
                parent=styles["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=11,
                leading=15,
                textColor=colors.HexColor("#9B2C2C"),
                spaceAfter=5,
            )
            cell_bold = ParagraphStyle(
                "CellBold",
                parent=styles["Normal"],
                fontName="Helvetica-Bold",
                fontSize=9,
                leading=12,
                textColor=colors.HexColor("#2D3748"),
            )
            cell_normal = ParagraphStyle(
                "CellNormal",
                parent=styles["Normal"],
                fontName="Helvetica",
                fontSize=9,
                leading=12,
                textColor=colors.HexColor("#4A5568"),
            )

            story = []

            # 1. Header
            story.append(Paragraph("AUTO-SETTLE AI — SURVEYOR CLAIMS REVIEW DOSSIER", title_style))
            story.append(Paragraph("Autonomous Claims Guardrail Escalation & Investigation Packet", subtitle_style))
            story.append(Spacer(1, 15))

            # 2. Metadata Table
            meta_data = [
                [Paragraph("Dossier ID:", cell_bold), Paragraph(dossier.dossier_id, cell_normal),
                 Paragraph("Compiled At:", cell_bold), Paragraph(dossier.compiled_at.strftime("%d %b %Y %H:%M UTC"), cell_normal)],
                [Paragraph("Claim ID:", cell_bold), Paragraph(str(dossier.claim_id), cell_normal),
                 Paragraph("Policy ID:", cell_bold), Paragraph(dossier.policy_id, cell_normal)],
                [Paragraph("Registration No:", cell_bold), Paragraph(dossier.registration_number, cell_normal),
                 Paragraph("Escalation Code:", cell_bold), Paragraph(f"<b>{dossier.escalation_code}</b>", ParagraphStyle("EscCode", parent=cell_bold, textColor=colors.HexColor("#C53030")))],
            ]
            meta_table = Table(meta_data, colWidths=[95, 175, 95, 175])
            meta_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF5F5")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#FED7D7")),
                ("PADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            story.append(meta_table)
            story.append(Spacer(1, 12))

            # 3. Escalation Trigger Summary
            story.append(Paragraph("Escalation Diagnostic Trigger & Recommended Action:", section_heading))
            trigger_data = [
                [Paragraph("Trigger Reason:", cell_bold), Paragraph(dossier.escalation_reason, cell_normal)],
                [Paragraph("Surveyor Action:", cell_bold), Paragraph(dossier.recommended_surveyor_action, cell_normal)],
            ]
            trigger_table = Table(trigger_data, colWidths=[120, 420])
            trigger_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7FAFC")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("PADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            story.append(trigger_table)
            story.append(Spacer(1, 12))

            # 4. Surveyor Physical Verification Checklist
            story.append(Paragraph("Surveyor Physical Site Inspection Checklist:", section_heading))
            checklist_data = []
            for idx, item in enumerate(dossier.surveyor_checklist, start=1):
                checklist_data.append([
                    Paragraph(f"[  ] <b>{idx}.</b>", cell_bold),
                    Paragraph(item, cell_normal),
                ])
            checklist_table = Table(checklist_data, colWidths=[40, 500])
            checklist_table.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("PADDING", (0, 0), (-1, -1), 5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story.append(checklist_table)
            story.append(Spacer(1, 12))

            # 5. Signoff Block
            sign_data = [
                [Paragraph("Assigned Surveyor Name: _______________________", cell_normal),
                 Paragraph("IRDAI License No: _______________________", cell_normal)],
                [Paragraph("Inspection Date: _______________________", cell_normal),
                 Paragraph("Surveyor Signature: _______________________", cell_normal)],
            ]
            sign_table = Table(sign_data, colWidths=[270, 270])
            sign_table.setStyle(TableStyle([
                ("PADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            story.append(sign_table)

            doc.build(story)
            pdf_bytes = buffer.getvalue()
            buffer.close()
            return pdf_bytes

        except Exception as e:
            logger.error(f"Failed to generate adjuster dossier PDF: {e}", exc_info=True)
            raise PDFGenerationError(f"PDF adjuster dossier generation failed: {e}")


reportlab_pdf_service = ReportLabPDFService()

