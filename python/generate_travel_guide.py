import os


def create_travel_guide():
    content = """# Travel Guide: June Vacation Options (6 People, 2 Families)

## Overview
This document compares two distinct vacation experiences for a group of 6 (including kids) traveling in the first week of June.

---

## Option 1: The "Monsoon Magic" (Coorg, Karnataka)
**Theme:** Tropical, Lush, Rainy, and Relaxing.

### 1. The Experience
*   **Climate:** High humidity, frequent rain, misty mornings, and very green landscapes.
*   **Activities:** Coffee plantation walks, visiting Abbey Falls, exploring Madikeri Fort, and enjoying luxury resort amenities.

*   **Best For:** Families who love nature, greenery, and a "staycation" vibe in high-end resorts.

### 2. Logistics & Budget
*   **Travel:** Fly Hyderabad $\\rightarrow$ Bangalore + Private Innova.
*   **Budget (Per Person):** ₹50,000 - ₹60,000.
*   **Accommodation:** Premium Plantation Resorts.

---

## Option 2: The "Mountain Summer" (Manali, Himachal Pradesh)
**Theme:** Alpine, Adventure, Sunny, and Cool.

### 1. The Experience
*   **Climate:** Pleasant and sunny in the valleys; cold and snowy at higher altitudes (Rohtang/Atal Tunnel).
*   **Activities:** Paragliding in Solang Valley, exploring Rohtang Pass, visiting ancient temples, and river rafting.
*   **Best For:** Families seeking adventure, snow, and a complete escape from the Indian summer heat.

### 2. Logistics & Budget
*   **Travel:** Fly Hyderabad $\\rightarrow$ Delhi + Long Drive (Private Innova).
*   **Budget (Per Person):** ₹55,000 - ₹65,000 (Higher due to longer travel and adventure costs).
*   **Accommodation:** Mountain Resorts or Boutique Hotels.

---

## Comparison Summary

| Feature | Coorg (South) | Manali (North) |
| :--- | :--- | :--- |
| **Weather** | Rainy & Misty | Sunny & Cool |
| **Landscape** | Tropical Greenery | Snow-capped Peaks |
| **Travel Effort** | Low (Easy access) | High (Longer drives) |
| **Primary Vibe** | Relaxation/Luxury | Adventure/Exploration |

## Final Recommendation
*   **Choose Coorg** if you want a low-stress, luxurious, and lush green experience where the rain is part of the charm.
*   **Choose Manali** if you want to escape the heat and are willing to undertake a longer journey for the thrill of snow and adventure.
"""

    file_path = "travel_guide.md"

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Successfully created: {os.path.abspath(file_path)}")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    create_travel_guide()
