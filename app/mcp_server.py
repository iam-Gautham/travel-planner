from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Travel Planner MCP Server")

@mcp.tool()
def search_flights(origin: str, destination: str, date: str) -> str:
    """Search for mock flights between origin and destination on a given date.
    
    Args:
        origin: Starting city or airport code.
        destination: Target city or airport code.
        date: Date of travel (YYYY-MM-DD).
    """
    return (
        f"Available Flights on {date} from {origin} to {destination}:\n"
        f"- SkyWays SW-101: Departure 08:00, Arrival 10:30. Price: $350 (Economy)\n"
        f"- JetBlue JB-442: Departure 14:00, Arrival 16:35. Price: $420 (Economy)\n"
        f"- AirExpress AE-89: Departure 19:30, Arrival 22:00. Price: $290 (Economy)\n"
    )

@mcp.tool()
def search_hotels(destination: str, checkin_date: str, checkout_date: str) -> str:
    """Search for mock hotels in a destination city for the specified dates.
    
    Args:
        destination: City name where the hotel is located.
        checkin_date: Arrival date (YYYY-MM-DD).
        checkout_date: Departure date (YYYY-MM-DD).
    """
    return (
        f"Lodging options in {destination} from {checkin_date} to {checkout_date}:\n"
        f"- Grand Plaza Hotel: 4.5 stars, Luxury Suite. Price: $180/night. Amenities: Free Wi-Fi, Pool, Gym.\n"
        f"- Cozy Corner B&B: 4.2 stars, Standard Room. Price: $95/night. Amenities: Free Breakfast, Wi-Fi.\n"
        f"- Urban Central Hostel: 3.8 stars, Shared Dorm. Price: $40/night. Amenities: Shared Kitchen, Wi-Fi.\n"
    )

@mcp.tool()
def get_weather_forecast(destination: str, date: str) -> str:
    """Get weather forecast for a destination city on a specific date.
    
    Args:
        destination: Target city or region.
        date: Date for the forecast (YYYY-MM-DD).
    """
    dest_lower = destination.lower()
    if "paris" in dest_lower:
        return f"Weather Forecast for Paris on {date}: Partly cloudy, 65°F (18°C). 20% chance of rain."
    elif "tokyo" in dest_lower:
        return f"Weather Forecast for Tokyo on {date}: Sunny, 72°F (22°C). 5% chance of rain."
    elif "london" in dest_lower:
        return f"Weather Forecast for London on {date}: Showers, 58°F (14°C). 75% chance of rain."
    else:
        return f"Weather Forecast for {destination} on {date}: Pleasant and clear, 70°F (21°C). 10% chance of rain."

@mcp.tool()
def calculate_travel_budget(flights_cost: float, hotels_cost_per_night: float, nights: int, daily_allowance: float) -> str:
    """Calculate the total estimated travel budget, summing flight costs, lodging, and daily allowances.
    
    Args:
        flights_cost: Round-trip flight cost in USD.
        hotels_cost_per_night: Cost of lodging per night in USD.
        nights: Number of nights of stay.
        daily_allowance: Estimated daily allowance for food, local transit, and activities in USD.
    """
    lodging_total = hotels_cost_per_night * nights
    allowance_total = daily_allowance * (nights + 1)
    total_cost = flights_cost + lodging_total + allowance_total
    return (
        f"Estimated Travel Budget breakdown:\n"
        f"- Flights: ${flights_cost:.2f}\n"
        f"- Lodging ({nights} nights @ ${hotels_cost_per_night:.2f}/night): ${lodging_total:.2f}\n"
        f"- Expenses ({nights + 1} days @ ${daily_allowance:.2f}/day): ${allowance_total:.2f}\n"
        f"-----------------------------------------\n"
        f"Total Estimated Budget: ${total_cost:.2f}"
    )

if __name__ == "__main__":
    mcp.run()
