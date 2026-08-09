from datetime import datetime, timedelta

from services.realtime_data import get_all_weather_data, get_weather_data, get_earthquake_data
from ai.decision_support import predict_hazard
from models import db, Incident

# Earthquake severity is judged from real USGS magnitude readings, not the
# rainfall/river/soil-moisture AI decision support call (which has no
# meaningful relationship to seismic magnitude).
EARTHQUAKE_ALERT_MAGNITUDE = 4.5
DEFAULT_POPULATION_DENSITY = 1200
CITY_POPULATION_DENSITY = {
    'Lipa': 1650,
    'Batangas': 2400,
    'Tanauan': 1900,
    'Calamba': 3800,
    'San Pablo': 2400,
    'Lucena': 1350,
    'Tagaytay': 1100,
    'Imus': 16000,
    'Dasmariñas': 12800,
    'Cavite': 6600,
    'Taytay': 13000,
    'Antipolo': 6300,
    'Quezon': 1100,
    'Rizal': 1100,
    'Carmona': 4200,
    'Alaminos': 900,
    'Nagcarlan': 1400,
    'San Fernando': 10300,
}


def _estimate_river_level(rainfall_mm):
    # No real gauge is available, so use a simple rainfall-derived proxy.
    return round(min(15.0, max(0.0, rainfall_mm / 10.0)), 2)


def _population_density_for_city(city):
    return CITY_POPULATION_DENSITY.get(city, DEFAULT_POPULATION_DENSITY)


def _magnitude_to_level(magnitude):
    if magnitude >= 6.0:
        return "Severe"
    if magnitude >= 5.5:
        return "High"
    if magnitude >= 5.0:
        return "Moderate"
    return "Low"


def _magnitude_to_score(magnitude):
    # Simple linear mapping for display purposes: M4.5 -> 50, M7.5+ -> 100
    score = (magnitude - 4.5) / (7.5 - 4.5) * 100
    return max(0.0, min(100.0, round(score, 1)))


def monitor_earthquakes(app):
    """Check real earthquake feed and raise an alert for significant events."""
    earthquake_data = get_earthquake_data()
    if not earthquake_data:
        app.logger.info("Earthquake monitoring skipped: no earthquake data available")
        return False

    created_any = False
    for quake in earthquake_data:
        magnitude = float(quake.get("magnitude") or 0)
        if magnitude < EARTHQUAKE_ALERT_MAGNITUDE:
            continue

        location = quake.get("location") or quake.get("place") or "CALABARZON region"
        quake_time = quake.get("time")

        recent_incident = Incident.query.filter_by(
            hazard_type="earthquake",
            location=location,
            alert=True,
        ).filter(Incident.created_at >= datetime.utcnow() - timedelta(hours=6)).order_by(Incident.created_at.desc()).first()

        if recent_incident:
            app.logger.info(
                "Earthquake monitoring: recent alert already exists for %s", location
            )
            continue

        incident = Incident(
            hazard_type="earthquake",
            location=location,
            rainfall_mm=0.0,
            river_level_m=None,
            humidity_pct=0.0,
            population_density=0,
            score=_magnitude_to_score(magnitude),
            level=_magnitude_to_level(magnitude),
            message=f"Magnitude {magnitude:.1f} earthquake detected near {location}.",
            alert=True,
            status='ACTIVE',
            reported_by='system',
        )
        db.session.add(incident)
        created_any = True
        app.logger.info(
            "Earthquake monitoring: created alert for M%.1f near %s", magnitude, location
        )

    if created_any:
        db.session.commit()
    else:
        db.session.rollback()

    return created_any


def monitor_hazards():
    from app import app

    with app.app_context():
        monitor_earthquakes(app)

        weather_by_city = get_all_weather_data()
        if not weather_by_city:
            app.logger.info("Hazard monitoring skipped: no weather data available")
            return

        created_any = False
        for city, weather_data in weather_by_city.items():
            if not weather_data:
                app.logger.info("Hazard monitoring skipped for %s: no weather data", city)
                continue

            rainfall_mm = float(weather_data.get("rainfall", 0) or 0)
            humidity_pct = float(weather_data.get("humidity", 0) or 0)
            river_level_m = _estimate_river_level(rainfall_mm)
            population_density = _population_density_for_city(city)

            hazard_configs = [
                {
                    "hazard_type": "flood",
                    "rainfall_mm": rainfall_mm,
                    "river_level_m": river_level_m,
                    "humidity_pct": humidity_pct,
                    "population_density": population_density,
                },
                {
                    "hazard_type": "landslide",
                    "rainfall_mm": rainfall_mm,
                    "river_level_m": river_level_m,
                    "humidity_pct": humidity_pct,
                    "population_density": population_density,
                },
            ]

            for config in hazard_configs:
                try:
                    prediction = predict_hazard(**config)
                except Exception as exc:
                    app.logger.warning(
                        "Hazard monitoring: failed to predict %s for %s: %s",
                        config["hazard_type"], city, exc,
                    )
                    continue

                if not prediction:
                    continue

                threshold = 50.0
                level = str(prediction.get("level") or '').strip().upper()
                if level in {'UNKNOWN', 'INSUFFICIENT_DATA', 'INSUFFICIENT DATA', 'INSUFFICIENT-DATA'}:
                    app.logger.warning(
                        "Hazard monitoring: %s in %s returned insufficient data (level %s) and will not be treated as a low-risk outcome.",
                        config["hazard_type"], city, prediction.get("level"),
                    )
                    continue
                if prediction.get("score", 0) < threshold:
                    app.logger.info(
                        "Hazard monitoring: %s in %s score %.1f below threshold %.1f",
                        config["hazard_type"], city,
                        prediction.get("score", 0),
                        threshold,
                    )
                    continue

                recent_incident = Incident.query.filter_by(
                    hazard_type=prediction.get("type", config["hazard_type"]),
                    location=city,
                    alert=True,
                ).filter(Incident.created_at >= datetime.utcnow() - timedelta(hours=6)).order_by(Incident.created_at.desc()).first()

                if recent_incident:
                    app.logger.info(
                        "Hazard monitoring: recent alert already exists for %s in %s",
                        prediction.get("type", config["hazard_type"]),
                        city,
                    )
                    continue

                incident = Incident(
                    hazard_type=prediction.get("type", config["hazard_type"]),
                    location=city,
                    rainfall_mm=rainfall_mm,
                    river_level_m=river_level_m,
                    humidity_pct=humidity_pct,
                    population_density=population_density,
                    score=float(prediction.get("score", 0) or 0),
                    level=prediction.get("level", "Moderate"),
                    message=prediction.get("message", "High hazard risk detected."),
                    alert=bool(prediction.get("alert", False)),
                    status='ACTIVE' if prediction.get("alert") else 'NEW',
                    reported_by='system',
                )
                db.session.add(incident)
                created_any = True

        if created_any:
            db.session.commit()
            app.logger.info("Created hazard incidents for monitored hazards in CALABARZON")
        else:
            db.session.rollback()
            app.logger.info("Hazard monitoring: no high-risk incidents created")
