"""Static vocabulary of the synthetic company: regions, categories, name parts.

Every name is invented from these lists. Emails use the reserved ``.example`` domain
(RFC 2606) and phone numbers the 555-01xx range reserved for fiction, so no generated
contact can reach a real person.
"""

from dataclasses import dataclass
from decimal import Decimal

REGIONS: dict[str, tuple[str, ...]] = {
    "Western Europe": ("FR", "BE", "NL", "LU"),
    "Southern Europe": ("ES", "IT", "PT"),
    "Central Europe": ("DE", "AT", "CH", "PL"),
    "Northern Europe": ("SE", "DK", "FI", "NO"),
    "UK & Ireland": ("GB", "IE"),
}
# Customers per region, relative.
REGION_WEIGHTS: dict[str, float] = {
    "Western Europe": 0.38,
    "Southern Europe": 0.17,
    "Central Europe": 0.22,
    "Northern Europe": 0.10,
    "UK & Ireland": 0.13,
}
# The company is French: French customers pay 20 % VAT; other EU customers are under the
# reverse-charge rule and non-EU customers are exports, both invoiced at 0 %.
HOME_COUNTRY = "FR"
HOME_VAT_RATE = Decimal("0.200")

LEGAL_FORMS: dict[str, str] = {
    "FR": "SAS", "BE": "SRL", "NL": "B.V.", "LU": "S.A.", "ES": "S.L.", "IT": "S.r.l.",
    "PT": "Lda", "DE": "GmbH", "AT": "GmbH", "CH": "AG", "PL": "Sp. z o.o.", "SE": "AB",
    "DK": "ApS", "FI": "Oy", "NO": "AS", "GB": "Ltd", "IE": "Ltd",
}  # fmt: skip

INDUSTRIES: tuple[str, ...] = (
    "Manufacturing", "Retail", "Healthcare", "Construction", "Hospitality", "Logistics",
    "Education", "Professional Services", "Public Sector", "Technology",
)  # fmt: skip


@dataclass(frozen=True)
class CategorySpec:
    name: str
    code: str
    nouns: tuple[str, ...]
    # List price range in 2023, euros.
    price_range: tuple[int, int]
    # Gross margin range of its products.
    margin_range: tuple[float, float]
    # Typical quantities per line, relative to office supplies.
    quantity_factor: float
    # Yearly list-price increase, applied every 1 January.
    yearly_increase: float


CATEGORIES: tuple[CategorySpec, ...] = (
    CategorySpec("Office Furniture", "FUR", ("Desk", "Chair", "Cabinet", "Shelf", "Table", "Locker"), (120, 900), (0.30, 0.45), 0.3, 0.04),
    CategorySpec("Office Supplies", "SUP", ("Paper Ream", "Binder", "Pen Box", "Notebook", "Stapler", "Folder"), (3, 40), (0.35, 0.55), 2.0, 0.03),
    CategorySpec("IT Hardware", "ITH", ("Laptop", "Monitor", "Docking Station", "Keyboard", "Headset", "Webcam"), (40, 1600), (0.12, 0.25), 0.4, 0.02),
    CategorySpec("Networking", "NET", ("Switch", "Router", "Access Point", "Patch Panel", "Cable Kit", "Firewall"), (30, 1200), (0.18, 0.30), 0.4, 0.02),
    CategorySpec("Printing", "PRT", ("Laser Printer", "Toner", "Ink Cartridge", "Scanner", "Label Printer", "Drum Unit"), (25, 700), (0.20, 0.40), 0.8, 0.03),
    CategorySpec("Cleaning & Hygiene", "CLN", ("Soap Refill", "Paper Towels", "Disinfectant", "Bin Liners", "Mop Kit", "Hand Dryer"), (4, 350), (0.30, 0.50), 1.5, 0.05),
    CategorySpec("Safety Equipment", "SAF", ("First Aid Kit", "Fire Extinguisher", "Safety Gloves", "Hi-Vis Vest", "Helmet", "Eyewash Station"), (6, 300), (0.30, 0.45), 1.0, 0.04),
    CategorySpec("Packaging", "PKG", ("Carton Box", "Bubble Wrap", "Tape Roll", "Pallet Wrap", "Mailer Bag", "Void Fill"), (2, 80), (0.25, 0.40), 2.0, 0.05),
    CategorySpec("Breakroom", "BRK", ("Coffee Beans", "Water Cooler", "Cup Pack", "Tea Box", "Microwave", "Kettle"), (5, 450), (0.30, 0.50), 1.2, 0.04),
    CategorySpec("Lighting", "LGT", ("LED Panel", "Desk Lamp", "Floodlight", "LED Tube", "Emergency Light", "Motion Sensor"), (15, 400), (0.28, 0.42), 0.8, 0.03),
)  # fmt: skip

BRANDS: tuple[str, ...] = (
    "Aurora", "Brixton", "Cobalt", "Delta", "Equinox", "Fjord", "Granite", "Helix",
    "Ivory", "Juniper", "Kestrel", "Lumen", "Meridian", "Nimbus", "Orion",
)  # fmt: skip

COMPANY_PREFIXES: tuple[str, ...] = (
    "Alpha", "Blue", "Central", "Civic", "Crest", "Euro", "First", "Grand", "Green",
    "High", "Inter", "Metro", "New", "North", "Nova", "Prime", "Royal", "South",
    "Summit", "United",
)  # fmt: skip
COMPANY_ROOTS: tuple[str, ...] = (
    "Anchor", "Arbor", "Atlas", "Beacon", "Birch", "Bridge", "Canyon", "Castle", "Cedar",
    "Coast", "Comet", "Copper", "Crown", "Dune", "Eagle", "Ember", "Falcon", "Field",
    "Forge", "Fox", "Garden", "Glacier", "Harbor", "Hawk", "Heath", "Hill", "Iron",
    "Island", "Lake", "Lantern", "Laurel", "Linden", "Maple", "Marble", "Meadow", "Mill",
    "Oak", "Ocean", "Pine", "Pioneer", "Quarry", "Raven", "Ridge", "River", "Rock",
    "Sage", "Silver", "Spring", "Star", "Stone", "Sun", "Tide", "Timber", "Tower",
    "Valley", "Willow", "Wind", "Wolf", "Yarrow", "Zephyr",
)  # fmt: skip
COMPANY_SECTOR_WORDS: dict[str, tuple[str, ...]] = {
    "Manufacturing": ("Industries", "Works", "Fabrication"),
    "Retail": ("Stores", "Retail", "Market"),
    "Healthcare": ("Clinics", "Health", "Care"),
    "Construction": ("Builders", "Construction", "Structures"),
    "Hospitality": ("Hotels", "Hospitality", "Resorts"),
    "Logistics": ("Logistics", "Freight", "Transport"),
    "Education": ("Academy", "Schools", "Learning"),
    "Professional Services": ("Partners", "Consulting", "Advisory"),
    "Public Sector": ("Services", "Agency", "Authority"),
    "Technology": ("Systems", "Digital", "Labs"),
}

SUPPLIER_NAMES: tuple[str, ...] = (
    "Acme Wholesale", "Baltic Trading", "Cardinal Supply", "Danube Distribution",
    "Elbe Components", "Fennic Imports", "Gallic Industrie", "Hanse Logistics",
    "Iberia Mayorista", "Jura Fournitures", "Kronos Electronics", "Loire Emballages",
    "Mistral Equipements", "Nordkap Supply", "Olympus Hygiene", "Po Valley Forniture",
    "Quantum Devices", "Rhine Office", "Seine Mobilier", "Tagus Packaging",
    "Ural Lighting", "Vistula Safety", "Weser Network", "Xanthe Print",
    "Ypres Furniture", "Zagros Cleaning",
)  # fmt: skip

FIRST_NAMES: tuple[str, ...] = (
    "Alice", "Ana", "Anders", "Bruno", "Camille", "Carlos", "Chiara", "Claire", "Daniel",
    "Elena", "Emma", "Erik", "Fatima", "Felix", "Giulia", "Hannah", "Hugo", "Ines",
    "Jan", "Julia", "Karim", "Lars", "Laura", "Leon", "Lucas", "Maria", "Marta",
    "Mathieu", "Mila", "Nina", "Noah", "Oliver", "Paula", "Pierre", "Rosa", "Sara",
    "Sofia", "Thomas", "Tomasz", "Yasmin",
)  # fmt: skip
LAST_NAMES: tuple[str, ...] = (
    "Andersen", "Bauer", "Bernard", "Bianchi", "Costa", "Dubois", "Eriksson", "Fernandes",
    "Fischer", "Garcia", "Hansen", "Jansen", "Kowalski", "Lambert", "Lopez", "Martin",
    "Meyer", "Moreau", "Murphy", "Nielsen", "Novak", "Petit", "Ricci", "Rossi",
    "Santos", "Schmidt", "Silva", "Smith", "Virtanen", "Wagner", "Walsh", "Weber",
)  # fmt: skip
JOB_TITLES: tuple[str, ...] = (
    "Purchasing Manager", "Office Manager", "Facility Manager", "Finance Director",
    "Procurement Officer", "Operations Manager", "Accounts Payable Clerk", "IT Manager",
)  # fmt: skip

PAYMENT_METHODS: tuple[str, ...] = ("bank_transfer", "card", "direct_debit", "cheque")
PAYMENT_METHOD_WEIGHTS: tuple[float, ...] = (0.62, 0.12, 0.20, 0.06)

# Relative order volume per calendar month: B2B, quiet in August, busy in the autumn.
SEASONALITY: dict[int, float] = {
    1: 0.85, 2: 0.90, 3: 1.05, 4: 1.00, 5: 1.00, 6: 1.05,
    7: 0.85, 8: 0.60, 9: 1.10, 10: 1.10, 11: 1.15, 12: 0.95,
}  # fmt: skip
YEARLY_GROWTH = 0.08
