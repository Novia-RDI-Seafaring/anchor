from pydantic import BaseModel


class PdfBBox(BaseModel):
    l: float
    t: float
    r: float
    b: float
    coord_origin: str = "BOTTOMLEFT"


class PdfCitationLocation(BaseModel):
    page: int
    bbox: PdfBBox | None = None


class PdfCitationDocument(BaseModel):
    filename: str
    mime_type: str | None = None


class PdfCitationRender(BaseModel):
    image_url: str
    pdf_url: str


class PdfCitation(BaseModel):
    id: str
    score: float
    text: str
    type: str
    headings: list[str] = []
    document: PdfCitationDocument
    location: PdfCitationLocation | None = None
    render: PdfCitationRender


class PdfSearchResponse(BaseModel):
    answer: str
    citations: list[PdfCitation]
