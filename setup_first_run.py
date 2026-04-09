"""
First-run setup script.
Creates placeholder boilerplate files if they do not exist.
Run once: python setup_first_run.py
"""
from pathlib import Path
from backend.config import BOILERPLATE_DIR, TEMPLATES_DIR

# uvicorn backend.main:app --host 127.0.0.1 --port 8765 --reload

PLACEHOLDERS = {
    # ── Finnish versions ──────────────────────────────────────────────────────
    "documentation_fi.txt": """\
6. Dokumentaatio

Visualisointiin sekä raportointiin käytettävät ohjelmistot määrittelee Toimittaja. Kirjallisen raportoinnin ja dokumentoinnin
tason ja laajuuden määrittelee Toimittaja. Kirjeenvaihtoon ja muuhun dokumentaatioon käytetään MS Office -ohjelmistoja.
Toimittajan projektipäälikkö vastaa oman projektiosuutensa projektidokumenttien toteutuksesta.
""",
    "quality_assurance_fi.txt": """\
7. Laadunvarmistus

Laadunvarmistus tässä projektissa toteutetaan SKOL:n konsultointi- ja asiantuntijapalveluiden yleisten sopimusehtojen
sekä niissä määriteltyjen tarjoussopimusperiaatteiden mukaisesti. Projektitiimi noudattaa vakiintuneita laatuprosesseja, joihin kuuluvat:

- Rakenteelliset koodi- ja tekniset katselmukset
- Testausprotokollat projektisuunnitelman mukaisesti
- Edistymiskatselmukset sovituissa projektin välitavoitteissa
- Lopullinen hyväksymistestaus asiakkaan kanssa

Poikkeamat laatuvaatimuksista dokumentoidaan ja käsitellään viipymättä.
""",
    "delivery_terms_fi.txt": """\
9. Yleiset toimitusehdot

Tämä tarjous ja siitä mahdollisesti syntyvä sopimus ovat SKOL:n konsultointi- ja asiantuntijapalveluiden
yleisten sopimusehtojen alaisia. Ehdot kattavat maksuehdot, immateriaalioikeudet, salassapidon,
vastuunrajoitukset ja riidanratkaisun.

Maksuehto: 14 päivää netto laskun päivämäärästä.
Asiakas vastaa tarvittavien pääsyoikeuksien, tietojen ja hyväksyntöjen toimittamisesta
oikea-aikaisesti, jotta projekti voidaan toteuttaa sovitun aikataulun mukaisesti.

Jäljennös yleisistä sopimusehdoista on liitteenä 1.
""",
    "payment_agreement_fi.txt": """\
Maksusopimus

Tämä tarjous on voimassa {payment_due_date} saakka.

Laskutus tapahtuu sovittujen projektin välitavoitteiden mukaisesti. Jokainen lasku erääntyy
14 päivän kuluessa laskun päivämäärästä. Viivästyneistä maksuista peritään viivästyskorko
korkolain (633/1982) mukaisesti.

Kaikki hinnat ovat ilman arvonlisäveroa, ellei toisin mainita. ALV lisätään laskutushetken
voimassaolevan verokannan mukaisesti.
""",

    # ── English versions ──────────────────────────────────────────────────────
    "documentation_en.txt": """\
6. Documentation

The software tools used for visualisation and reporting are determined by the Supplier.
The level and scope of written reporting and documentation are defined by the Supplier.
MS Office applications are used for correspondence and other documentation.
The Supplier's project manager is responsible for the project documentation within their scope.
""",
    "quality_assurance_en.txt": """\
7. Quality Assurance

Quality assurance in this project is carried out in accordance with SKOL general terms
and conditions for consulting and expert services, and the offer contracting principles
defined therein. The project team follows established quality processes including:

- Structured code reviews and technical reviews
- Testing protocols as defined in the project specification
- Progress reviews at defined project milestones
- Final acceptance testing with the customer

Any deviations from quality requirements will be documented and addressed promptly.
""",
    "delivery_terms_en.txt": """\
9. Generic Terms of Delivery

This offer and any resulting agreement are subject to the general terms and conditions
for consulting and expert services (SKOL). The terms cover payment conditions,
intellectual property rights, confidentiality, liability limitations, and dispute resolution.

Payment terms: 14 days net from invoice date.
The customer is responsible for providing necessary access, information, and approvals
in a timely manner to enable project execution according to the agreed schedule.

A copy of the full general terms and conditions is attached as Attachment 1.
""",
    "payment_agreement_en.txt": """\
Payment Agreement

This offer is valid until {payment_due_date}.

Invoicing will follow the agreed project milestones. Each invoice is due within 14 days
of the invoice date. Late payments are subject to a late payment interest as defined in
the Finnish Interest Act (Korkolaki 633/1982).

All prices are exclusive of VAT unless otherwise stated. VAT will be added at the
applicable rate at the time of invoicing.
""",
}


def run():
    BOILERPLATE_DIR.mkdir(parents=True, exist_ok=True)
    for filename, content in PLACEHOLDERS.items():
        dest = BOILERPLATE_DIR / filename
        if not dest.exists():
            dest.write_text(content, encoding="utf-8")
            print(f"Created: {dest}")
        else:
            print(f"Already exists (skipped): {dest}")

    # Create a minimal offer template if missing
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    template_path = TEMPLATES_DIR / "offer_template.docx"
    if not template_path.exists():
        try:
            from docx import Document
            from docx.shared import Pt, Cm
            from docx.enum.style import WD_STYLE_TYPE
            doc = Document()
            for section in doc.sections:
                section.top_margin    = Cm(2.5)
                section.bottom_margin = Cm(2.5)
                section.left_margin   = Cm(3.0)
                section.right_margin  = Cm(2.5)
            # Set default font
            style = doc.styles['Normal']
            style.font.name = 'Calibri'
            style.font.size = Pt(11)
            doc.save(str(template_path))
            print(f"Created offer template: {template_path}")
        except ImportError:
            print("python-docx not installed yet — template will be created on first run.")

    print("\nSetup complete.")
    print(f"Boilerplate files are in: {BOILERPLATE_DIR}")
    print("Edit them to match your actual SKOL and delivery terms text.")


if __name__ == "__main__":
    run()
