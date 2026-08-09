"""Simple seed helpers for local/demo data."""

from models import Barangay, Municipality, Province, db


GEOGRAPHY_SEED = [
    {
        "province": {
            "code": "BAT",
            "name": "Batangas",
        },
        "municipalities": [
            {
                "code": "LIPA",
                "name": "Lipa City",
                "barangays": [
                    "Santo Tomas",
                    "Banaybanay",
                    "Marawoy",
                    "Mabini",
                ],
            },
            {
                "code": "TANAUAN",
                "name": "Tanauan City",
                "barangays": [
                    "Janopol",
                    "Poblacion",
                    "Altura",
                    "Darasa",
                ],
            },
        ],
    },
]


def seed_geography_data():
    """Populate a small set of province/municipality/barangay records for local use."""
    for province_data in GEOGRAPHY_SEED:
        province = Province.query.filter_by(code=province_data["province"]["code"]).first()
        if province is None:
            province = Province(code=province_data["province"]["code"], name=province_data["province"]["name"])
            db.session.add(province)
            db.session.flush()

        for municipality_data in province_data["municipalities"]:
            municipality = Municipality.query.filter_by(code=municipality_data["code"]).first()
            if municipality is None:
                municipality = Municipality(province_id=province.id, code=municipality_data["code"], name=municipality_data["name"])
                db.session.add(municipality)
                db.session.flush()

            for barangay_name in municipality_data["barangays"]:
                existing_barangay = Barangay.query.filter_by(municipality_id=municipality.id, name=barangay_name).first()
                if existing_barangay is None:
                    db.session.add(Barangay(municipality_id=municipality.id, name=barangay_name))

    db.session.commit()


def seed_demo_data():
    seed_geography_data()


if __name__ == "__main__":
    seed_demo_data()
