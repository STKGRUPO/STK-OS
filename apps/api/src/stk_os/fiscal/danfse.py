from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path

import qrcode
from lxml import etree
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)

# STK Financeiro - DANFSe v2.0
# Gerador alinhado à Nota Técnica SE/CGNFS-e nº 008/2026 - versão 1.02 (14/07/2026).
# O DANFSe é gerado exclusivamente a partir do XML da NFS-e retornado pela SEFIN Nacional.

NS = {"n": "http://www.sped.fazenda.gov.br/nfse"}

PAGE_W, PAGE_H = A4
X0_CM = 0.30
CONTENT_W_CM = 20.40
COL_X_CM = [0.30, 5.41, 10.51, 15.62]
COL_W_CM = [5.09, 5.09, 5.09, 5.08]
LIGHT_GRAY = 0.95


def _register_fonts():
    # A NT 008 v1.02 determina Arial para labels/titulos e Microsoft Sans Serif
    # para conteudos. Nao empacotamos fontes: no Windows usamos as fontes locais.
    label = "Helvetica"
    label_bold = "Helvetica-Bold"
    content = "Helvetica"
    candidates = [
        ("ArialLocal", r"C:\Windows\Fonts\arial.ttf"),
        ("ArialLocalBold", r"C:\Windows\Fonts\arialbd.ttf"),
        ("MSSansLocal", r"C:\Windows\Fonts\micross.ttf"),
    ]
    for name, path in candidates:
        try:
            if os.path.exists(path):
                pdfmetrics.registerFont(TTFont(name, path))
        except Exception as error:
            logger.debug("DANFSe font registration failed", exc_info=error)
    names = set(pdfmetrics.getRegisteredFontNames())
    if "ArialLocal" in names:
        label = "ArialLocal"
    if "ArialLocalBold" in names:
        label_bold = "ArialLocalBold"
    if "MSSansLocal" in names:
        content = "MSSansLocal"
    return label, label_bold, content


LABEL_FONT, LABEL_BOLD, CONTENT_FONT = _register_fonts()


STATUS = {
    "100": "NFS-e Gerada",
    "102": "NFS-e de Decisão Judicial",
    "103": "NFS-e Avulsa",
    "107": "NFS-e MEI",
}
TP_EMIT = {"1": "Prestador", "2": "Tomador", "3": "Intermediário"}
SIMPLES = {
    "1": "Não optante",
    "2": "Optante - Microempreendedor Individual (MEI)",
    "3": "Optante - Microempresa ou Empresa de Pequeno Porte (ME/EPP)",
}
REG_AP_SN = {
    "1": "Regime de apuração dos tributos federais e municipal pelo Simples Nacional",
    "2": "Tributos federais pelo Simples Nacional e ISSQN por fora do Simples Nacional",
    "3": "Tributos federais e municipal por fora do Simples Nacional",
}
TRIB_ISS = {
    "1": "Operação Tributável",
    "2": "Imunidade",
    "3": "Exportação de serviço",
    "4": "Não Incidência",
}
RET_ISS = {
    "1": "Não Retido",
    "2": "Retido pelo Tomador",
    "3": "Retido pelo Intermediário",
}
SOCIAL_RET = {
    "0": "PIS/COFINS/CSLL Não Retidos",
    "1": "PIS/COFINS Retidos",
    "2": "PIS/COFINS Não Retidos",
    "3": "PIS/COFINS/CSLL Retidos",
    "4": "PIS/COFINS Retidos, CSLL Não Retido",
    "5": "PIS Retido, COFINS/CSLL Não Retidos",
    "6": "COFINS Retido, PIS/CSLL Não Retidos",
    "7": "PIS Não Retido, COFINS/CSLL Retidos",
    "8": "PIS/COFINS Não Retidos, CSLL Retido",
    "9": "COFINS Não Retido, PIS/CSLL Retidos",
}
FINALIDADE = {"0": "NFS-e regular"}
REG_ESP = {
    "0": "-",
    "1": "Microempresa municipal",
    "2": "Estimativa",
    "3": "Sociedade de profissionais",
    "4": "Cooperativa",
    "5": "MEI",
    "6": "ME/EPP do Simples Nacional",
    "9": "Outros",
}
IMUNIDADE = {
    "1": "Patrimônio, renda ou serviços, uns dos outros",
    "2": "Templos de qualquer culto",
    "3": "Patrimônio, renda ou serviços dos partidos políticos",
    "4": "Livros, jornais, periódicos e o papel destinado a sua impressão",
    "5": "Fonogramas e videofonogramas musicais produzidos no Brasil",
}
SUSPENSAO = {
    "1": "Exigibilidade Suspensa por Decisão Judicial",
    "2": "Exigibilidade Suspensa por Processo Administrativo",
}
BENEFICIO_MUN = {"1": "Isenção", "2": "Redução", "3": "Diferimento", "4": "Outros"}


def _text(root, xpath: str, default: str = "") -> str:
    vals = root.xpath(xpath, namespaces=NS)
    if not vals:
        return default
    value = vals[0]
    if hasattr(value, "text"):
        return (value.text or default).strip()
    return str(value).strip()


def _first(root, *xpaths: str, default: str = "") -> str:
    for xpath in xpaths:
        value = _text(root, xpath, "")
        if value:
            return value
    return default


def _attr(root, xpath: str, attr: str, default: str = "") -> str:
    vals = root.xpath(xpath, namespaces=NS)
    return vals[0].get(attr, default) if vals else default


def _dec(value: str) -> Decimal:
    try:
        return Decimal(str(value or "0").replace(",", "."))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _has_value(value: str) -> bool:
    return str(value or "").strip() != ""


def _money(value: str, dash_if_blank: bool = True) -> str:
    if not _has_value(value):
        return "-" if dash_if_blank else "R$ 0,00"
    try:
        num = _dec(value)
        raw = f"{num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {raw}"
    except Exception:
        return str(value)


def _pct(value: str, dash_if_blank: bool = True) -> str:
    if not _has_value(value):
        return "-" if dash_if_blank else "0,00 %"
    try:
        return f"{_dec(value):.2f} %".replace(".", ",")
    except Exception:
        return str(value)


def _format_id(value: str) -> str:
    raw = re.sub(r"[^A-Za-z0-9]", "", value or "").upper()
    if len(raw) == 14:
        # Valido para CNPJ numerico e para o novo CNPJ alfanumerico.
        return f"{raw[:2]}.{raw[2:5]}.{raw[5:8]}/{raw[8:12]}-{raw[12:]}"
    if len(raw) == 11 and raw.isdigit():
        return f"{raw[:3]}.{raw[3:6]}.{raw[6:9]}-{raw[9:]}"
    return value or "-"


def _phone(value: str) -> str:
    d = re.sub(r"\D", "", value or "")
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return value or "-"


def _cep(value: str) -> str:
    d = re.sub(r"\D", "", value or "")
    return f"{d[:2]}.{d[2:5]}-{d[5:]}" if len(d) == 8 else (value or "-")


def _ibge(value: str) -> str:
    d = re.sub(r"\D", "", value or "")
    return f"{d[:2]}.{d[2:]}" if len(d) == 7 else (value or "-")


def _ctrib(value: str) -> str:
    d = re.sub(r"\D", "", value or "")
    return f"{d[:2]}.{d[2:4]}.{d[4:6]}" if len(d) == 6 else (value or "-")


def _nbs(value: str) -> str:
    d = re.sub(r"\D", "", value or "")
    return f"{d[0]}.{d[1:5]}.{d[5:7]}.{d[7:9]}" if len(d) == 9 else (value or "-")


def _date(value: str) -> str:
    if not value:
        return "-"
    try:
        return datetime.fromisoformat(value[:10]).strftime("%d/%m/%Y")
    except Exception:
        return value


def _datetime(value: str) -> str:
    if not value:
        return "-"
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return value


def _address(*parts: str) -> str:
    values = [str(p).strip() for p in parts if str(p or "").strip()]
    return ", ".join(values) if values else "-"


def _fit(c: canvas.Canvas, text: str, font: str, size: float, max_width: float) -> str:
    text = str(text if text is not None else "-") or "-"
    if c.stringWidth(text, font, size) <= max_width:
        return text
    ellipsis = "..."
    available = max_width - c.stringWidth(ellipsis, font, size)
    out = text
    while out and c.stringWidth(out, font, size) > available:
        out = out[:-1]
    return (out.rstrip() + ellipsis) if out else ellipsis


def _wrap_lines(
    c: canvas.Canvas, text: str, font: str, size: float, max_width: float, max_lines: int = 99
):
    words = str(text or "-").split()
    lines = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if not current or c.stringWidth(candidate, font, size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if not lines:
        lines = ["-"]
    if len(lines) == max_lines:
        lines[-1] = _fit(c, lines[-1], font, size, max_width)
    return lines


def _top_y(top_cm: float) -> float:
    return PAGE_H - top_cm * cm


def _shade(c: canvas.Canvas, x_cm: float, top_cm: float, w_cm: float, h_cm: float):
    c.saveState()
    c.setFillGray(LIGHT_GRAY)
    c.rect(x_cm * cm, _top_y(top_cm + h_cm), w_cm * cm, h_cm * cm, stroke=0, fill=1)
    c.restoreState()


def _hline(
    c: canvas.Canvas,
    top_cm: float,
    x_cm: float = X0_CM,
    w_cm: float = CONTENT_W_CM,
    width: float = 0.5,
):
    c.saveState()
    c.setLineWidth(width)
    y = _top_y(top_cm)
    c.line(x_cm * cm, y, (x_cm + w_cm) * cm, y)
    c.restoreState()


def _vline(c: canvas.Canvas, x_cm: float, top_cm: float, h_cm: float, width: float = 0.5):
    c.saveState()
    c.setLineWidth(width)
    c.line(x_cm * cm, _top_y(top_cm), x_cm * cm, _top_y(top_cm + h_cm))
    c.restoreState()


def _block_title(
    c: canvas.Canvas, text: str, x_cm: float, top_cm: float, w_cm: float, h_cm: float = 0.63
):
    _shade(c, x_cm, top_cm, w_cm, h_cm)
    c.setFillGray(0)
    c.setFont(LABEL_BOLD, 7)
    c.drawString(
        (x_cm + 0.10) * cm,
        _top_y(top_cm + 0.30),
        _fit(c, text.upper(), LABEL_BOLD, 7, (w_cm - 0.18) * cm),
    )


def _field(
    c: canvas.Canvas,
    label: str,
    value: str,
    x_cm: float,
    top_cm: float,
    w_cm: float,
    h_cm: float = 0.63,
    label_size: float = 6,
    value_size: float = 7,
    label_upper: bool = False,
    shaded: bool = False,
):
    if shaded:
        _shade(c, x_cm, top_cm, w_cm, h_cm)
    label_text = label.upper() if label_upper else label
    c.setFillGray(0)
    c.setFont(LABEL_BOLD, label_size)
    c.drawString(
        (x_cm + 0.10) * cm,
        _top_y(top_cm + 0.20),
        _fit(c, label_text, LABEL_BOLD, label_size, (w_cm - 0.18) * cm),
    )
    c.setFont(CONTENT_FONT, value_size)
    c.drawString(
        (x_cm + 0.10) * cm,
        _top_y(top_cm + 0.49),
        _fit(c, value or "-", CONTENT_FONT, value_size, (w_cm - 0.18) * cm),
    )


def _text_row(
    c: canvas.Canvas,
    text: str,
    x_cm: float,
    top_cm: float,
    w_cm: float,
    h_cm: float,
    size: float = 7,
    bold: bool = False,
    pad_cm: float = 0.10,
    max_lines: int = 10,
):
    font = LABEL_BOLD if bold else CONTENT_FONT
    c.setFont(font, size)
    max_w = (w_cm - 2 * pad_cm) * cm
    lines = _wrap_lines(c, text or "-", font, size, max_w, max_lines=max_lines)
    leading = max(size + 1.0, 8.0)
    y = _top_y(top_cm + 0.24)
    for line in lines:
        if y < _top_y(top_cm + h_cm - 0.08):
            break
        c.drawString((x_cm + pad_cm) * cm, y, _fit(c, line, font, size, max_w))
        y -= leading


def _label_and_wrapped_value(
    c: canvas.Canvas,
    label: str,
    value: str,
    x_cm: float,
    top_cm: float,
    w_cm: float,
    h_cm: float,
    max_lines: int = 8,
):
    c.setFont(LABEL_BOLD, 6)
    c.drawString((x_cm + 0.10) * cm, _top_y(top_cm + 0.20), label)
    c.setFont(CONTENT_FONT, 7)
    max_w = (w_cm - 0.20) * cm
    lines = _wrap_lines(c, value or "-", CONTENT_FONT, 7, max_w, max_lines=max_lines)
    y = _top_y(top_cm + 0.50)
    for line in lines:
        if y < _top_y(top_cm + h_cm - 0.08):
            break
        c.drawString((x_cm + 0.10) * cm, y, _fit(c, line, CONTENT_FONT, 7, max_w))
        y -= 8.5


def _identity(root, base: str):
    return _first(root, f"{base}/n:CNPJ", f"{base}/n:CPF", f"{base}/n:NIF", default="")


def _party_data(root, base: str, fallback_emit: bool = False):
    ident = _identity(root, base)
    name = _text(root, f"{base}/n:xNome")
    im = _text(root, f"{base}/n:IM")
    phone = _text(root, f"{base}/n:fone")
    email = _text(root, f"{base}/n:email")

    cmun = _first(root, f"{base}/n:end/n:endNac/n:cMun", f"{base}/n:endNac/n:cMun")
    uf = _first(root, f"{base}/n:end/n:endNac/n:UF", f"{base}/n:endNac/n:UF")
    cep = _first(root, f"{base}/n:end/n:endNac/n:CEP", f"{base}/n:endNac/n:CEP")
    log = _first(
        root, f"{base}/n:end/n:xLgr", f"{base}/n:end/n:endNac/n:xLgr", f"{base}/n:endNac/n:xLgr"
    )
    nro = _first(
        root, f"{base}/n:end/n:nro", f"{base}/n:end/n:endNac/n:nro", f"{base}/n:endNac/n:nro"
    )
    cpl = _first(
        root, f"{base}/n:end/n:xCpl", f"{base}/n:end/n:endNac/n:xCpl", f"{base}/n:endNac/n:xCpl"
    )
    bairro = _first(
        root,
        f"{base}/n:end/n:xBairro",
        f"{base}/n:end/n:endNac/n:xBairro",
        f"{base}/n:endNac/n:xBairro",
    )
    city_ext = _first(root, f"{base}/n:end/n:endExt/n:xCidade", f"{base}/n:endExt/n:xCidade")
    postal_ext = _first(root, f"{base}/n:end/n:endExt/n:cEndPost", f"{base}/n:endExt/n:cEndPost")
    country = _first(root, f"{base}/n:end/n:endExt/n:cPais", f"{base}/n:endExt/n:cPais")

    if fallback_emit:
        # Na DPS do prestador, xNome/endereco podem ser omitidos. A SEFIN devolve esses
        # dados no grupo infNFSe/emit. Para telefone/e-mail, priorizamos a DPS, como a NT 008.
        emit = "/n:NFSe/n:infNFSe/n:emit"
        name = name or _text(root, f"{emit}/n:xNome")
        cmun = cmun or _text(root, f"{emit}/n:enderNac/n:cMun")
        uf = uf or _text(root, f"{emit}/n:enderNac/n:UF")
        cep = cep or _text(root, f"{emit}/n:enderNac/n:CEP")
        log = log or _text(root, f"{emit}/n:enderNac/n:xLgr")
        nro = nro or _text(root, f"{emit}/n:enderNac/n:nro")
        cpl = cpl or _text(root, f"{emit}/n:enderNac/n:xCpl")
        bairro = bairro or _text(root, f"{emit}/n:enderNac/n:xBairro")
        phone = phone or _text(root, f"{emit}/n:fone")
        email = email or _text(root, f"{emit}/n:email")

    return {
        "id": ident,
        "name": name,
        "im": im,
        "phone": phone,
        "email": email,
        "cmun": cmun,
        "uf": uf,
        "cep": cep,
        "address": _address(log, nro, cpl, bairro),
        "city_ext": city_ext,
        "postal_ext": postal_ext,
        "country": country,
    }


def _party_exists(data: dict) -> bool:
    return any(data.get(k) for k in ("id", "name", "phone", "email", "cmun", "city_ext"))


def _draw_party(
    c: canvas.Canvas,
    top_cm: float,
    title: str,
    data: dict,
    municipality_name: str = "",
    fallback_uf: str = "",
) -> float:
    # 4 linhas de 0,64 cm, conforme modelo do Anexo I.
    row = 0.64
    _hline(c, top_cm)
    _block_title(c, title, COL_X_CM[0], top_cm, COL_W_CM[0], row)
    _field(
        c, "CNPJ / CPF / NIF", _format_id(data.get("id", "")), COL_X_CM[1], top_cm, COL_W_CM[1], row
    )
    _field(
        c,
        "Indicador Municipal (Inscrição)",
        data.get("im") or "-",
        COL_X_CM[2],
        top_cm,
        COL_W_CM[2],
        row,
    )
    _field(c, "Telefone", _phone(data.get("phone", "")), COL_X_CM[3], top_cm, COL_W_CM[3], row)

    city = municipality_name or data.get("city_ext") or "-"
    uf = data.get("uf") or fallback_uf or "-"
    city_uf = f"{city} / {uf}" if city != "-" else "-"
    code = data.get("cmun") or "-"
    cep = data.get("cep") or data.get("postal_ext") or "-"
    code_cep = f"{_ibge(code)} / {_cep(cep)}" if code != "-" or cep != "-" else "-"

    _field(
        c, "Nome / Nome Empresarial", data.get("name") or "-", COL_X_CM[0], top_cm + row, 10.19, row
    )
    _field(c, "Município / Sigla UF", city_uf, COL_X_CM[2], top_cm + row, COL_W_CM[2], row)
    _field(c, "Código IBGE / CEP", code_cep, COL_X_CM[3], top_cm + row, COL_W_CM[3], row)

    _field(c, "Endereço", data.get("address") or "-", COL_X_CM[0], top_cm + 2 * row, 10.19, row)
    _field(c, "E-mail", data.get("email") or "-", COL_X_CM[2], top_cm + 2 * row, 10.19, row)

    # Esta ultima linha e preenchida pelo chamador quando se trata do prestador.
    return top_cm + 3 * row


def _draw_compact_absent(c: canvas.Canvas, top_cm: float, message: str) -> float:
    h = 0.32
    _hline(c, top_cm)
    c.setFont(CONTENT_FONT, 7)
    c.drawCentredString((X0_CM + CONTENT_W_CM / 2) * cm, _top_y(top_cm + 0.23), message)
    _hline(c, top_cm + h)
    return top_cm + h


def _draw_full_party_three_rows(
    c: canvas.Canvas,
    top_cm: float,
    title: str,
    data: dict,
    municipality_name: str = "",
    fallback_uf: str = "",
) -> float:
    row = 0.64
    _hline(c, top_cm)
    _block_title(c, title, COL_X_CM[0], top_cm, COL_W_CM[0], row)
    _field(
        c, "CNPJ / CPF / NIF", _format_id(data.get("id", "")), COL_X_CM[1], top_cm, COL_W_CM[1], row
    )
    _field(
        c,
        "Indicador Municipal (Inscrição)",
        data.get("im") or "-",
        COL_X_CM[2],
        top_cm,
        COL_W_CM[2],
        row,
    )
    _field(c, "Telefone", _phone(data.get("phone", "")), COL_X_CM[3], top_cm, COL_W_CM[3], row)
    city = municipality_name or data.get("city_ext") or "-"
    uf = data.get("uf") or fallback_uf or "-"
    city_uf = f"{city} / {uf}" if city != "-" else "-"
    code = data.get("cmun") or "-"
    cep = data.get("cep") or data.get("postal_ext") or "-"
    code_cep = f"{_ibge(code)} / {_cep(cep)}" if code != "-" or cep != "-" else "-"
    _field(
        c, "Nome / Nome Empresarial", data.get("name") or "-", COL_X_CM[0], top_cm + row, 10.19, row
    )
    _field(c, "Município / Sigla UF", city_uf, COL_X_CM[2], top_cm + row, COL_W_CM[2], row)
    _field(c, "Código IBGE / CEP", code_cep, COL_X_CM[3], top_cm + row, COL_W_CM[3], row)
    _field(c, "Endereço", data.get("address") or "-", COL_X_CM[0], top_cm + 2 * row, 10.19, row)
    _field(c, "E-mail", data.get("email") or "-", COL_X_CM[2], top_cm + 2 * row, 10.19, row)
    bottom = top_cm + 3 * row
    _hline(c, bottom)
    return bottom


def generate_danfse(
    xml_path: str | Path,
    pdf_path: str | Path,
    logo_path: str | Path | None = None,
    include_canhoto: bool = True,
    taker_municipality_name: str = "",
    taker_uf: str = "",
) -> Path:
    xml_path = Path(xml_path)
    pdf_path = Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    root = etree.parse(str(xml_path)).getroot()
    inf = "/n:NFSe/n:infNFSe"
    dps = inf + "/n:DPS/n:infDPS"

    inf_id = _attr(root, inf, "Id")
    chave = inf_id[3:] if inf_id.startswith("NFS") else inf_id
    nfse_num = _text(root, inf + "/n:nNFSe")
    competencia = _text(root, dps + "/n:dCompet")
    dh_proc = _text(root, inf + "/n:dhProc")
    dps_num = _text(root, dps + "/n:nDPS")
    dps_serie = _text(root, dps + "/n:serie")
    dh_dps = _text(root, dps + "/n:dhEmi")
    tp_amb = _text(root, dps + "/n:tpAmb")
    amb_ger = _text(root, inf + "/n:ambGer")
    tp_emit = _text(root, dps + "/n:tpEmit")
    cstat = _text(root, inf + "/n:cStat")
    fin_nfse = _text(root, dps + "/n:IBSCBS/n:finNFSe")

    municipio = _text(root, inf + "/n:xLocEmi")
    uf_emit = _text(root, inf + "/n:emit/n:enderNac/n:UF")

    prest = _party_data(root, dps + "/n:prest", fallback_emit=True)
    toma = _party_data(root, dps + "/n:toma")
    dest = _party_data(root, dps + "/n:IBSCBS/n:dest")
    interm = _party_data(root, dps + "/n:interm")

    op_sn = _text(root, dps + "/n:prest/n:regTrib/n:opSimpNac")
    reg_ap_sn = _text(root, dps + "/n:prest/n:regTrib/n:regApTribSN")
    reg_esp = _text(root, dps + "/n:prest/n:regTrib/n:regEspTrib")

    ctrib_nac = _text(root, dps + "/n:serv/n:cServ/n:cTribNac")
    ctrib_mun = _text(root, dps + "/n:serv/n:cServ/n:cTribMun")
    xtrib_nac = _text(root, inf + "/n:xTribNac")
    xtrib_mun = _text(root, inf + "/n:xTribMun")
    nbs = _text(root, dps + "/n:serv/n:cServ/n:cNBS")
    xloc_prest = _text(root, inf + "/n:xLocPrestacao")
    country_prest = _text(root, dps + "/n:serv/n:locPrest/n:cPaisPrestacao")
    desc = _text(root, dps + "/n:serv/n:cServ/n:xDescServ")

    trib_mun = dps + "/n:valores/n:trib/n:tribMun"
    iss_type = _text(root, trib_mun + "/n:tribISSQN")
    iss_ret = _text(root, trib_mun + "/n:tpRetISSQN")
    xloc_incid = _text(root, inf + "/n:xLocIncid")
    country_incid = _text(root, trib_mun + "/n:cPaisResult")
    tp_imun = _text(root, trib_mun + "/n:tpImunidade")
    susp = _text(root, trib_mun + "/n:exigSusp/n:tpSusp")
    nproc = _text(root, trib_mun + "/n:exigSusp/n:nProcesso")
    bc = _text(root, inf + "/n:valores/n:vBC")
    aliq_iss = _text(root, inf + "/n:valores/n:pAliqAplic")
    viss = _text(root, inf + "/n:valores/n:vISSQN")
    tp_bm = _text(root, inf + "/n:valores/n:tpBM")
    vcalc_bm = _first(
        root,
        inf + "/n:valores/n:vCalcBM",
        trib_mun + "/n:BM/n:vCalcBM",
        trib_mun + "/n:BM/n:vRedBCBM",
    )
    vded_red = _first(
        root,
        dps + "/n:valores/n:vDedRed",
        inf + "/n:IBSCBS/n:valores/n:vDR",
        inf + "/n:IBSCBS/n:valores/n:vCalcDR",
    )
    vdesc_incond = _text(root, dps + "/n:valores/n:vDescCondIncond/n:vDescIncond")
    vdesc_cond = _text(root, dps + "/n:valores/n:vDescCondIncond/n:vDescCond")

    trib_fed = dps + "/n:valores/n:trib/n:tribFed"
    irrf = _text(root, trib_fed + "/n:vRetIRRF")
    previd = _text(root, trib_fed + "/n:vRetCP")
    vret_csll = _text(root, trib_fed + "/n:vRetCSLL")
    pcf = trib_fed + "/n:piscofins"
    vpis = _text(root, pcf + "/n:vPis")
    vcofins = _text(root, pcf + "/n:vCofins")
    tp_social = _text(root, pcf + "/n:tpRetPisCofins")
    if tp_social == "1":
        social_value = str(_dec(vret_csll) + _dec(vpis) + _dec(vcofins))
        pis_debito = "0.00"
        cofins_debito = "0.00"
    else:
        social_value = vret_csll
        pis_debito = vpis
        cofins_debito = vcofins

    bruto = _text(root, dps + "/n:valores/n:vServPrest/n:vServ") or bc
    total_ret = _text(root, inf + "/n:valores/n:vTotalRet")
    liquido = _text(root, inf + "/n:valores/n:vLiq")

    # IBS/CBS - caminhos definidos na NT 008 v1.02.
    dps_ibscbs = dps + "/n:IBSCBS"
    nfse_ibscbs = inf + "/n:IBSCBS"
    g_ibs = dps_ibscbs + "/n:valores/n:trib/n:gIBSCBS"
    cst = _text(root, g_ibs + "/n:CST")
    cclass = _text(root, g_ibs + "/n:cClassTrib")
    cindop = _text(root, dps_ibscbs + "/n:cIndOp")
    cloc_ibs = _text(root, nfse_ibscbs + "/n:cLocalidadeIncid")
    xloc_ibs = _text(root, nfse_ibscbs + "/n:xLocalidadeIncid")
    uf_ibs = _text(root, nfse_ibscbs + "/n:UFIncid")
    ibs_vcalc_ree = _text(root, nfse_ibscbs + "/n:valores/n:vCalcReeRepRes")
    ibs_vbc = _text(root, nfse_ibscbs + "/n:valores/n:vBC")
    pred_uf = _text(root, nfse_ibscbs + "/n:valores/n:uf/n:pRedAliqUF")
    pred_mun = _text(root, nfse_ibscbs + "/n:valores/n:mun/n:pRedAliqMun")
    pred_cbs = _text(root, nfse_ibscbs + "/n:valores/n:fed/n:pRedAliqCBS")
    pibs_uf = _text(root, nfse_ibscbs + "/n:valores/n:uf/n:pIBSUF")
    pibs_mun = _text(root, nfse_ibscbs + "/n:valores/n:mun/n:pIBSMun")
    pefet_mun = _text(root, nfse_ibscbs + "/n:valores/n:mun/n:pAliqEfetMun")
    pefet_uf = _text(root, nfse_ibscbs + "/n:valores/n:uf/n:pAliqEfetUF")
    pcbs = _text(root, nfse_ibscbs + "/n:valores/n:fed/n:pCBS")
    pefet_cbs = _text(root, nfse_ibscbs + "/n:valores/n:fed/n:pAliqEfetCBS")
    vibs_mun = _text(root, nfse_ibscbs + "/n:totCIBS/n:gIBS/n:gIBSMunTot/n:vIBSMun")
    vibs_uf = _text(root, nfse_ibscbs + "/n:totCIBS/n:gIBS/n:gIBSUFTot/n:vIBSUF")
    vibs_tot = _text(root, nfse_ibscbs + "/n:totCIBS/n:gIBS/n:vIBSTot")
    vcbs = _text(root, nfse_ibscbs + "/n:totCIBS/n:gCBS/n:vCBS")
    vtot_nf = _text(root, nfse_ibscbs + "/n:totCIBS/n:vTotNF")
    ibs_present = bool(
        root.xpath(nfse_ibscbs, namespaces=NS) or root.xpath(dps_ibscbs, namespaces=NS)
    )

    # NT 008: Exclusoes e Reducoes = desconto incond. + vCalcReeRepRes + ISSQN + PIS + COFINS.
    excl_red = _dec(vdesc_incond) + _dec(ibs_vcalc_ree) + _dec(viss) + _dec(vpis) + _dec(vcofins)
    excl_red_value = (
        f"{excl_red:.2f}"
        if any(_has_value(v) for v in (vdesc_incond, ibs_vcalc_ree, viss, vpis, vcofins))
        else ""
    )
    total_ibs_cbs = _dec(vibs_tot) + _dec(vcbs)
    # O DANFSe oficial do Emissor Nacional exibe R$ 0,00 nos dois totais
    # de IBS/CBS quando o XML nao traz valores apurados. Mantemos essa
    # representacao para paridade visual/documental com o modelo nacional.
    total_ibs_cbs_value = f"{total_ibs_cbs:.2f}" if ibs_present else "0.00"
    vtot_nf_display = vtot_nf if _has_value(vtot_nf) else "0.00"

    # Informacoes complementares conforme ordem da NT 008.
    info = dps + "/n:serv/n:infoCompl"
    info_parts = []
    xinf = _text(root, info + "/n:xInfComp")
    if xinf:
        info_parts.append(f"Inf. Cont.: {xinf}")
    ch_sub = _text(root, dps + "/n:subst/n:chSubstda")
    if ch_sub:
        info_parts.append(f"NFS-e Subst.: {ch_sub}")
    doc_ref = _text(root, info + "/n:docRef")
    if doc_ref:
        info_parts.append(f"Doc. Ref.: {doc_ref}")
    c_obra = _text(root, dps + "/n:serv/n:obra/n:cObra")
    if c_obra:
        info_parts.append(f"Cód. Obra: {c_obra}")
    insc_imob = _text(root, dps_ibscbs + "/n:imovel/n:inscImobFisc")
    if insc_imob:
        info_parts.append(f"Insc. Imob.: {insc_imob}")
    evt = _text(root, dps + "/n:serv/n:atvEvento/n:idAtvEvt")
    if evt:
        info_parts.append(f"Cód. Evt.: {evt}")
    doc_tec = _text(root, info + "/n:idDocTec")
    if doc_tec:
        info_parts.append(f"Doc. Tec.: {doc_tec}")
    pedido = _text(root, info + "/n:xPed")
    if pedido:
        info_parts.append(f"Núm. Ped.: {pedido}")
    item_ped = _first(root, info + "/n:gItemPed/n:xItemPed", info + "/n:xItemPed")
    if item_ped:
        info_parts.append(f"Item Ped.: {item_ped}")
    xout = _text(root, info + "/n:xOutInf")
    if xout:
        info_parts.append(f"Inf. A. T. Mun.: {xout}")

    p_fed = _text(root, dps + "/n:valores/n:trib/n:totTrib/n:pTotTrib/n:pTotTribFed")
    p_est = _text(root, dps + "/n:valores/n:trib/n:totTrib/n:pTotTrib/n:pTotTribEst")
    p_mun = _text(root, dps + "/n:valores/n:trib/n:totTrib/n:pTotTrib/n:pTotTribMun")
    v_fed = _text(root, dps + "/n:valores/n:trib/n:totTrib/n:vTotTrib/n:vTotTribFed")
    v_est = _text(root, dps + "/n:valores/n:trib/n:totTrib/n:vTotTrib/n:vTotTribEst")
    v_mun = _text(root, dps + "/n:valores/n:trib/n:totTrib/n:vTotTrib/n:vTotTribMun")
    if any(_has_value(v) for v in (p_fed, p_est, p_mun)):
        trib_line = (
            "Totais aproximados dos Tributos cfe. Lei nº 12.741/2012: "
            f"Federais: {_pct(p_fed, dash_if_blank=False)}; "
            f"Estaduais: {_pct(p_est, dash_if_blank=False)}; "
            f"Municipais: {_pct(p_mun, dash_if_blank=False)};"
        )
    elif any(_has_value(v) for v in (v_fed, v_est, v_mun)):
        trib_line = (
            "Totais aproximados dos Tributos cfe. Lei nº 12.741/2012: "
            f"Federais: {_money(v_fed, dash_if_blank=False)}; "
            f"Estaduais: {_money(v_est, dash_if_blank=False)}; "
            f"Municipais: {_money(v_mun, dash_if_blank=False)};"
        )
    else:
        trib_line = (
            "Totais aproximados dos Tributos cfe. Lei nº 12.741/2012: "
            "Federais: -; Estaduais: -; Municipais: -;"
        )

    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    c.setTitle(f"DANFSe {nfse_num or ''}")
    c.setAuthor("Sistema Nacional NFS-e / STK Financeiro")

    # Borda externa: 1 pt, margem de 0,15 cm.
    c.setLineWidth(1)
    c.rect(0.15 * cm, 0.15 * cm, PAGE_W - 0.30 * cm, PAGE_H - 0.30 * cm, stroke=1, fill=0)

    # CABECALHO - 0,30 cm / 1,16 cm
    top = 0.30
    header_h = 1.16
    _shade(c, X0_CM, top, CONTENT_W_CM, header_h)
    if logo_path and Path(logo_path).exists():
        try:
            c.drawImage(
                ImageReader(str(logo_path)),
                0.49 * cm,
                _top_y(0.44 + 0.85),
                width=4.00 * cm,
                height=0.85 * cm,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception as error:
            logger.debug("DANFSe logo rendering failed", exc_info=error)
    c.setFillGray(0)
    c.setFont(LABEL_BOLD, 9)
    c.drawCentredString((5.41 + 10.19 / 2) * cm, _top_y(0.66), "DANFSe v2.0")
    c.drawCentredString((5.41 + 10.19 / 2) * cm, _top_y(0.99), "Documento Auxiliar da NFS-e")
    if tp_amb == "2":
        c.setFillColorRGB(0.90, 0.0, 0.0)
        c.drawCentredString((5.41 + 10.19 / 2) * cm, _top_y(1.26), "NFS-e SEM VALIDADE JURÍDICA")
        c.setFillGray(0)
    c.setFont(CONTENT_FONT, 8)
    c.drawString(15.75 * cm, _top_y(0.59), f"Município: {municipio or '-'} - {uf_emit or '-'}")
    c.setFont(CONTENT_FONT, 6)
    c.drawString(15.75 * cm, _top_y(0.88), f"Ambiente Gerador: {amb_ger or '-'}")
    c.drawString(15.75 * cm, _top_y(1.10), f"Tipo de Ambiente: {tp_amb or '-'}")
    _hline(c, top + header_h)

    # DADOS DA NFS-e - posicoes do item 2.4.5.
    _hline(c, 1.48)
    _field(
        c,
        "CHAVE DE ACESSO DA NFS-e",
        chave or "-",
        X0_CM,
        1.48,
        15.30,
        0.77,
        label_size=7,
        value_size=7,
        label_upper=True,
    )
    _field(
        c,
        "NÚMERO DA NFS-e",
        nfse_num or "-",
        X0_CM,
        2.27,
        5.09,
        0.67,
        label_size=7,
        value_size=7,
        label_upper=True,
    )
    _field(
        c,
        "COMPETÊNCIA DA NFS-e",
        _date(competencia),
        5.41,
        2.27,
        5.09,
        0.67,
        label_size=7,
        value_size=7,
        label_upper=True,
    )
    _field(
        c,
        "DATA E HORA DA EMISSÃO DA NFS-e",
        _datetime(dh_proc),
        10.51,
        2.27,
        5.09,
        0.67,
        label_size=7,
        value_size=7,
        label_upper=True,
    )
    _field(
        c,
        "NÚMERO DA DPS",
        dps_num or "-",
        X0_CM,
        2.96,
        5.09,
        0.67,
        label_size=7,
        value_size=7,
        label_upper=True,
    )
    _field(
        c,
        "SÉRIE DA DPS",
        dps_serie or "-",
        5.41,
        2.96,
        5.09,
        0.67,
        label_size=7,
        value_size=7,
        label_upper=True,
    )
    _field(
        c,
        "DATA E HORA DA EMISSÃO DA DPS",
        _datetime(dh_dps),
        10.51,
        2.96,
        5.09,
        0.67,
        label_size=7,
        value_size=7,
        label_upper=True,
    )
    _field(
        c,
        "EMITENTE DA NFS-e",
        TP_EMIT.get(tp_emit, tp_emit or "-"),
        X0_CM,
        3.65,
        5.09,
        0.67,
        label_size=7,
        value_size=7,
        label_upper=True,
        shaded=True,
    )
    _field(
        c,
        "SITUAÇÃO DA NFS-e",
        STATUS.get(cstat, cstat or "-"),
        5.41,
        3.65,
        5.09,
        0.67,
        label_size=7,
        value_size=7,
        label_upper=True,
    )
    _field(
        c,
        "FINALIDADE",
        FINALIDADE.get(fin_nfse, fin_nfse or "-"),
        10.51,
        3.65,
        5.09,
        0.67,
        label_size=7,
        value_size=7,
        label_upper=True,
    )

    qr_url = f"https://www.nfse.gov.br/ConsultaPublica/?tpc=1&chave={chave}"
    qr = qrcode.QRCode(version=None, box_size=6, border=1)
    qr.add_data(qr_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    c.drawImage(
        ImageReader(bio),
        17.48 * cm,
        _top_y(1.67 + 1.52),
        width=1.52 * cm,
        height=1.52 * cm,
        mask="auto",
    )
    qr_text = (
        "A autenticidade desta NFS-e pode ser verificada pela leitura deste código QR "
        "ou pela consulta da chave de acesso no portal nacional da NFS-e"
    )
    lines = _wrap_lines(c, qr_text, CONTENT_FONT, 6, 4.72 * cm, max_lines=3)
    c.setFont(CONTENT_FONT, 6)
    qy = _top_y(3.49)
    for line in lines:
        c.drawString(15.80 * cm, qy, line)
        qy -= 7
    _hline(c, 4.32)

    # PRESTADOR
    top = 4.34
    row = 0.64
    _hline(c, top)
    _block_title(c, "PRESTADOR / FORNECEDOR", COL_X_CM[0], top, COL_W_CM[0], row)
    _field(c, "CNPJ / CPF / NIF", _format_id(prest["id"]), COL_X_CM[1], top, COL_W_CM[1], row)
    _field(
        c, "Indicador Municipal (Inscrição)", prest["im"] or "-", COL_X_CM[2], top, COL_W_CM[2], row
    )
    _field(c, "Telefone", _phone(prest["phone"]), COL_X_CM[3], top, COL_W_CM[3], row)
    _field(c, "Nome / Nome Empresarial", prest["name"] or "-", COL_X_CM[0], top + row, 10.19, row)
    _field(
        c,
        "Município / Sigla UF",
        f"{municipio or '-'} / {uf_emit or '-'}",
        COL_X_CM[2],
        top + row,
        COL_W_CM[2],
        row,
    )
    prest_code = (
        f"{_ibge(prest['cmun'])} / {_cep(prest['cep'])}" if prest["cmun"] or prest["cep"] else "-"
    )
    _field(c, "Código IBGE / CEP", prest_code, COL_X_CM[3], top + row, COL_W_CM[3], row)
    _field(c, "Endereço", prest["address"] or "-", COL_X_CM[0], top + 2 * row, 10.19, row)
    _field(c, "E-mail", prest["email"] or "-", COL_X_CM[2], top + 2 * row, 10.19, row)
    _field(
        c,
        "Simples Nacional na Data de Competência",
        SIMPLES.get(op_sn, op_sn or "-"),
        COL_X_CM[0],
        top + 3 * row,
        5.09,
        row,
    )
    _field(
        c,
        "Regime de Apuração Tributária pelo SN",
        REG_AP_SN.get(reg_ap_sn, reg_ap_sn or "-"),
        5.41,
        top + 3 * row,
        10.19,
        row,
    )
    top += 4 * row
    _hline(c, top)

    # TOMADOR - quando identificado, tres linhas.
    if _party_exists(toma):
        _block_title(c, "TOMADOR / ADQUIRENTE", COL_X_CM[0], top, COL_W_CM[0], row)
        _field(c, "CNPJ / CPF / NIF", _format_id(toma["id"]), COL_X_CM[1], top, COL_W_CM[1], row)
        _field(
            c,
            "Indicador Municipal (Inscrição)",
            toma["im"] or "-",
            COL_X_CM[2],
            top,
            COL_W_CM[2],
            row,
        )
        _field(c, "Telefone", _phone(toma["phone"]), COL_X_CM[3], top, COL_W_CM[3], row)
        _field(
            c, "Nome / Nome Empresarial", toma["name"] or "-", COL_X_CM[0], top + row, 10.19, row
        )
        # No leiaute XML nacional do endereço do tomador (TCEnderNac), o endereço
        # nacional traz cMun + CEP; xMun/UF não fazem parte desse grupo. O Portal
        # Nacional resolve o nome/UF a partir do código IBGE. Nosso DANFSe local
        # usa, quando disponível, o município/UF já salvos no cadastro do cliente.
        toma_city = (taker_municipality_name or toma["city_ext"] or "-").strip()
        toma_uf_display = (taker_uf or toma["uf"] or "-").strip().upper()
        _field(
            c,
            "Município / Sigla UF",
            f"{toma_city} / {toma_uf_display}" if toma_city != "-" else "-",
            COL_X_CM[2],
            top + row,
            COL_W_CM[2],
            row,
        )
        toma_code = (
            f"{_ibge(toma['cmun'])} / {_cep(toma['cep'] or toma['postal_ext'])}"
            if toma["cmun"] or toma["cep"] or toma["postal_ext"]
            else "-"
        )
        _field(c, "Código IBGE / CEP", toma_code, COL_X_CM[3], top + row, COL_W_CM[3], row)
        _field(c, "Endereço", toma["address"] or "-", COL_X_CM[0], top + 2 * row, 10.19, row)
        _field(c, "E-mail", toma["email"] or "-", COL_X_CM[2], top + 2 * row, 10.19, row)
        top += 3 * row
        _hline(c, top)
    else:
        top = _draw_compact_absent(
            c, top, "TOMADOR/ADQUIRENTE DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e"
        )

    # DESTINATARIO
    if _party_exists(dest):
        if (
            dest.get("id")
            and toma.get("id")
            and re.sub(r"\W", "", dest["id"]) == re.sub(r"\W", "", toma["id"])
        ):
            top = _draw_compact_absent(
                c, top, "O DESTINATÁRIO É O PRÓPRIO TOMADOR/ADQUIRENTE DA OPERAÇÃO"
            )
        else:
            top = _draw_full_party_three_rows(c, top, "DESTINATÁRIO DA OPERAÇÃO", dest)
    else:
        top = _draw_compact_absent(c, top, "DESTINATÁRIO DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e")

    # INTERMEDIARIO
    if _party_exists(interm):
        top = _draw_full_party_three_rows(c, top, "INTERMEDIÁRIO DA OPERAÇÃO", interm)
    else:
        top = _draw_compact_absent(c, top, "INTERMEDIÁRIO DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e")

    # SERVICO PRESTADO
    service_top = top
    _hline(c, service_top)
    _block_title(c, "SERVIÇO PRESTADO", COL_X_CM[0], service_top, COL_W_CM[0], row)
    ctrib_value = f"{_ctrib(ctrib_nac)} / {_ctrib(ctrib_mun) if ctrib_mun else '-'}"
    _field(
        c,
        "Código de Tributação Nacional/Municipal",
        ctrib_value,
        COL_X_CM[1],
        service_top,
        COL_W_CM[1],
        row,
    )
    _field(c, "Código da NBS", _nbs(nbs), COL_X_CM[2], service_top, COL_W_CM[2], row)
    loc_serv = f"{xloc_prest or '-'} / {uf_emit or '-'} / {country_prest or '-'}"
    _field(
        c,
        "Local da Prestação / Sigla UF / País",
        loc_serv,
        COL_X_CM[3],
        service_top,
        COL_W_CM[3],
        row,
    )
    trib_desc = xtrib_mun or xtrib_nac or "-"
    _text_row(c, trib_desc, X0_CM, service_top + row, CONTENT_W_CM, 0.38, size=7, max_lines=1)
    service_desc_h = 0.96
    _label_and_wrapped_value(
        c,
        "Descrição do Serviço",
        desc or "-",
        X0_CM,
        service_top + row + 0.38,
        CONTENT_W_CM,
        service_desc_h,
        max_lines=4,
    )
    top = service_top + row + 0.38 + service_desc_h
    _hline(c, top)

    # TRIBUTACAO MUNICIPAL (ISSQN)
    iss_top = top
    _block_title(c, "TRIBUTAÇÃO MUNICIPAL (ISSQN)", COL_X_CM[0], iss_top, COL_W_CM[0], row)
    _field(
        c,
        "Tipo de Tributação do ISSQN",
        TRIB_ISS.get(iss_type, iss_type or "-"),
        COL_X_CM[1],
        iss_top,
        COL_W_CM[1],
        row,
    )
    loc_incid = f"{xloc_incid or '-'} / {uf_emit or '-'} / {country_incid or '-'}"
    _field(
        c,
        "Município / Sigla UF / País de Incidência do ISSQN",
        loc_incid,
        COL_X_CM[2],
        iss_top,
        10.19,
        row,
    )
    cursor = iss_top + row

    # Linhas opcionais da tributacao municipal somente se existirem dados.
    if any(_has_value(v) for v in (tp_imun, susp, nproc)) or (reg_esp and reg_esp != "0"):
        _field(
            c,
            "Regime Especial de Tributação do ISSQN",
            REG_ESP.get(reg_esp, reg_esp or "-"),
            COL_X_CM[0],
            cursor,
            COL_W_CM[0],
            row,
        )
        _field(
            c,
            "Tipo de Imunidade do ISSQN",
            IMUNIDADE.get(tp_imun, tp_imun or "-"),
            COL_X_CM[1],
            cursor,
            COL_W_CM[1],
            row,
        )
        _field(
            c,
            "Suspensão da Exigibilidade do ISSQN",
            SUSPENSAO.get(susp, susp or "-"),
            COL_X_CM[2],
            cursor,
            COL_W_CM[2],
            row,
        )
        _field(c, "Número Processo Suspensão", nproc or "-", COL_X_CM[3], cursor, COL_W_CM[3], row)
        cursor += row
    if any(_has_value(v) for v in (tp_bm, vcalc_bm, vded_red, vdesc_incond)):
        _field(
            c,
            "Benefício Municipal",
            BENEFICIO_MUN.get(tp_bm, tp_bm or "-"),
            COL_X_CM[0],
            cursor,
            COL_W_CM[0],
            row,
        )
        _field(c, "Cálculo do BM", _money(vcalc_bm), COL_X_CM[1], cursor, COL_W_CM[1], row)
        _field(
            c, "Total Deduções/Reduções", _money(vded_red), COL_X_CM[2], cursor, COL_W_CM[2], row
        )
        _field(
            c,
            "Desconto Incondicionado",
            _money(vdesc_incond),
            COL_X_CM[3],
            cursor,
            COL_W_CM[3],
            row,
        )
        cursor += row
    _field(c, "BC ISSQN", _money(bc), COL_X_CM[0], cursor, COL_W_CM[0], row)
    _field(c, "Alíquota Aplicada", _pct(aliq_iss), COL_X_CM[1], cursor, COL_W_CM[1], row)
    _field(
        c,
        "Retenção do ISSQN",
        RET_ISS.get(iss_ret, iss_ret or "-"),
        COL_X_CM[2],
        cursor,
        COL_W_CM[2],
        row,
    )
    _field(c, "ISSQN Apurado", _money(viss), COL_X_CM[3], cursor, COL_W_CM[3], row)
    top = cursor + row
    _hline(c, top)

    # TRIBUTACAO FEDERAL (EXCETO CBS)
    fed_top = top
    _block_title(c, "TRIBUTAÇÃO FEDERAL (EXCETO CBS)", COL_X_CM[0], fed_top, COL_W_CM[0], row)
    _field(c, "IRRF", _money(irrf), COL_X_CM[1], fed_top, COL_W_CM[1], row)
    _field(
        c,
        "Contribuição Previdenciária - Retida",
        _money(previd),
        COL_X_CM[2],
        fed_top,
        COL_W_CM[2],
        row,
    )
    _field(
        c,
        "Contribuições Sociais - Retidas",
        _money(social_value),
        COL_X_CM[3],
        fed_top,
        COL_W_CM[3],
        row,
    )
    _field(
        c,
        "PIS - Débito Apuração Própria",
        _money(pis_debito),
        COL_X_CM[0],
        fed_top + row,
        COL_W_CM[0],
        row,
    )
    _field(
        c,
        "COFINS - Débito Apuração Própria",
        _money(cofins_debito),
        COL_X_CM[1],
        fed_top + row,
        COL_W_CM[1],
        row,
    )
    social_desc = f"{tp_social} - {SOCIAL_RET.get(tp_social, tp_social)}" if tp_social else "-"
    _field(
        c,
        "Descrição Contrib. Sociais - Retidas",
        social_desc,
        COL_X_CM[2],
        fed_top + row,
        10.19,
        row,
    )
    top = fed_top + 2 * row
    _hline(c, top)

    # TRIBUTACAO IBS/CBS - 4 linhas.
    ibs_top = top
    _block_title(c, "TRIBUTAÇÃO IBS/CBS", COL_X_CM[0], ibs_top, COL_W_CM[0], row)
    _field(
        c,
        "CST / cClassTrib",
        f"{cst or '-'} / {cclass or '-'}",
        COL_X_CM[1],
        ibs_top,
        COL_W_CM[1],
        row,
    )
    op_loc = (
        f"{cindop or '-'} / {_ibge(cloc_ibs) if cloc_ibs else '-'} / "
        f"{xloc_ibs or '-'} / {uf_ibs or '-'}"
    )
    _field(
        c,
        "Indicador de Operação / Código IBGE Incidência / Município Incidência / Sigla UF",
        op_loc,
        COL_X_CM[2],
        ibs_top,
        10.19,
        row,
    )
    _field(
        c,
        "Exclusões e Reduções da Base de Cálculo",
        _money(excl_red_value),
        COL_X_CM[0],
        ibs_top + row,
        COL_W_CM[0],
        row,
    )
    _field(
        c,
        "Base de Cálculo Após Exclusões e Reduções",
        _money(ibs_vbc),
        COL_X_CM[1],
        ibs_top + row,
        COL_W_CM[1],
        row,
    )
    red_aliq = f"{_pct(pred_uf)} / {_pct(pred_mun)} / {_pct(pred_cbs)}"
    _field(
        c,
        "Red. Alíquota IBS / Red. Alíquota CBS",
        red_aliq,
        COL_X_CM[2],
        ibs_top + row,
        COL_W_CM[2],
        row,
    )
    aliq_ibs = f"{_pct(pibs_uf)} / {_pct(pibs_mun)}"
    _field(c, "Alíquota - IBS UF / IBS Mun", aliq_ibs, COL_X_CM[3], ibs_top + row, COL_W_CM[3], row)
    _field(
        c,
        "Alíq. Efetiva Municipal - IBS",
        _pct(pefet_mun),
        COL_X_CM[0],
        ibs_top + 2 * row,
        COL_W_CM[0],
        row,
    )
    _field(
        c,
        "Valor Apurado Municipal - IBS",
        _money(vibs_mun),
        COL_X_CM[1],
        ibs_top + 2 * row,
        COL_W_CM[1],
        row,
    )
    _field(
        c,
        "Alíq. Efetiva Estadual - IBS",
        _pct(pefet_uf),
        COL_X_CM[2],
        ibs_top + 2 * row,
        COL_W_CM[2],
        row,
    )
    _field(
        c,
        "Valor Apurado Estadual - IBS",
        _money(vibs_uf),
        COL_X_CM[3],
        ibs_top + 2 * row,
        COL_W_CM[3],
        row,
    )
    _field(
        c,
        "Valor Total Apurado - IBS",
        _money(vibs_tot),
        COL_X_CM[0],
        ibs_top + 3 * row,
        COL_W_CM[0],
        row,
    )
    _field(c, "Alíquota - CBS", _pct(pcbs), COL_X_CM[1], ibs_top + 3 * row, COL_W_CM[1], row)
    _field(
        c,
        "Alíquota Efetiva - CBS",
        _pct(pefet_cbs),
        COL_X_CM[2],
        ibs_top + 3 * row,
        COL_W_CM[2],
        row,
    )
    _field(
        c,
        "Valor Total Apurado - CBS",
        _money(vcbs),
        COL_X_CM[3],
        ibs_top + 3 * row,
        COL_W_CM[3],
        row,
    )
    top = ibs_top + 4 * row
    _hline(c, top)

    # VALOR TOTAL DA NFS-e - 2 linhas.
    total_top = top
    _block_title(c, "VALOR TOTAL DA NFS-e", COL_X_CM[0], total_top, COL_W_CM[0], 0.67)
    _field(
        c,
        "VALOR DA OPERAÇÃO / SERVIÇO",
        _money(bruto),
        COL_X_CM[1],
        total_top,
        COL_W_CM[1],
        0.67,
        label_size=6,
        value_size=7,
        label_upper=True,
    )
    _field(
        c,
        "Desconto Incondicionado",
        _money(vdesc_incond),
        COL_X_CM[2],
        total_top,
        COL_W_CM[2],
        0.67,
    )
    _field(
        c, "Desconto Condicionado", _money(vdesc_cond), COL_X_CM[3], total_top, COL_W_CM[3], 0.67
    )
    _field(
        c,
        "Total das Retenções (ISSQN / Federais)",
        _money(total_ret),
        COL_X_CM[0],
        total_top + 0.67,
        COL_W_CM[0],
        0.67,
    )
    _field(
        c,
        "VALOR LÍQUIDO DA NFS-e",
        _money(liquido),
        COL_X_CM[1],
        total_top + 0.67,
        COL_W_CM[1],
        0.67,
        label_size=6,
        value_size=7,
        label_upper=True,
    )
    _field(
        c,
        "Total do IBS/CBS",
        _money(total_ibs_cbs_value, dash_if_blank=False),
        COL_X_CM[2],
        total_top + 0.67,
        COL_W_CM[2],
        0.67,
    )
    _field(
        c,
        "VALOR LÍQUIDO DA NFS-e + IBS/CBS",
        _money(vtot_nf_display, dash_if_blank=False),
        COL_X_CM[3],
        total_top + 0.67,
        COL_W_CM[3],
        0.67,
        label_size=6,
        value_size=7,
        label_upper=True,
        shaded=True,
    )
    top = total_top + 1.34
    _hline(c, top)

    # INFORMACOES COMPLEMENTARES. O canhoto e opcional, mas habilitado por padrao
    # para ficar equivalente ao DANFSe oficial do Emissor Nacional.
    canhoto_top = 28.10 if include_canhoto else 29.05
    info_title_h = 0.39
    _shade(c, X0_CM, top, CONTENT_W_CM, info_title_h)
    c.setFont(LABEL_BOLD, 7)
    c.drawString((X0_CM + 0.10) * cm, _top_y(top + 0.27), "INFORMAÇÕES COMPLEMENTARES")
    _hline(c, top)
    info_content_top = top + info_title_h
    info_content_h = max(0.60, canhoto_top - info_content_top)
    info_text = " | ".join(info_parts)
    if info_text:
        _text_row(
            c,
            info_text,
            X0_CM,
            info_content_top,
            CONTENT_W_CM,
            min(info_content_h, 1.15),
            size=7,
            max_lines=3,
        )
        trib_y = info_content_top + min(0.72, info_content_h - 0.20)
    else:
        trib_y = info_content_top + 0.18
    if trib_y < canhoto_top - 0.20:
        _text_row(c, trib_line, X0_CM, trib_y, CONTENT_W_CM, 0.70, size=7, max_lines=2)
    _hline(c, canhoto_top)

    if include_canhoto:
        h = 0.67
        c.setLineWidth(0.5)
        c.rect(X0_CM * cm, _top_y(canhoto_top + h), CONTENT_W_CM * cm, h * cm, stroke=1, fill=0)
        _vline(c, 5.41, canhoto_top, h)
        _vline(c, 10.51, canhoto_top, h)
        _field(
            c,
            "DATA CIENTIFICAÇÃO:",
            " ",
            X0_CM,
            canhoto_top,
            5.09,
            h,
            label_size=6,
            value_size=7,
            label_upper=True,
        )
        _field(
            c,
            "IDENTIFICAÇÃO E ASSINATURA",
            " ",
            5.41,
            canhoto_top,
            5.09,
            h,
            label_size=6,
            value_size=7,
            label_upper=True,
        )
        _field(
            c,
            "Nº NFS-e / CHAVE NFS-e",
            f"{nfse_num or '-'} / {chave or '-'}",
            10.51,
            canhoto_top,
            10.19,
            h,
            label_size=6,
            value_size=7,
            label_upper=True,
        )

    c.save()
    return pdf_path
