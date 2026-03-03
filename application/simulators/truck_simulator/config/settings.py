import random, os

NUM_TRUCKS = 10
UPDATE_INTERVAL = 2  # seconds

# Example Morocco cities (lon, lat)
CITIES = {
    "Casablanca": (-7.5898, 33.5731),
    "Rabat": (-6.8416, 34.0209),
    "Marrakech": (-8.0089, 31.6295),
    "Tanger": (-5.8126, 35.7595),
    "Agadir": (-9.5981, 30.4278),
    "Fes": (-4.9806, 34.0346),
    "Meknes": (-5.5551, 33.8933),
    "Oujda": (-1.9116, 34.6818),
    "Nador": (-2.9331, 35.1686),
    "Kenitra": (-6.5897, 34.2610),
    "El Jadida": (-8.5070, 33.2550),
    "Safi": (-9.2338, 32.2990),
    "Tetouan": (-5.3689, 35.5713),
    "Beni Mellal": (-6.3700, 32.3378),
    "Khouribga": (-6.9058, 33.6111),
    "Settat": (-7.6111, 33.0113),
    "Ifrane": (-5.1169, 33.5265),
    "Essaouira": (-9.7594, 31.5085),
    "Ouarzazate": (-6.9094, 30.9333),
    "Al Hoceima": (-3.9343, 35.2513)
}

KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "truck-gps")

