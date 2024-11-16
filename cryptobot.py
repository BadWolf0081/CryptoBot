import discord
import requests
import json
import os
from discord.ext import tasks
from datetime import datetime

# Configuration
CACHE_FILE = 'crypto_cache.json'  # Cache file to store tracked crypto data
IMAGES_FOLDER = 'images'  # Folder where the symbol images are stored

# CEX.IO new API URL
CEX_IO_API_URL = 'https://trade.cex.io/api/spot/rest-public/get_ticker'

# Intents configuration
intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent for receiving commands

# Initialize the Discord client
client = discord.Client(intents=intents)

# Helper function to get cryptocurrency data from CEX.IO API
def get_crypto_data(symbol, fiat):
    payload = {
        'pairs': [f"{symbol}-{fiat}"]
    }
    try:
        response = requests.post(CEX_IO_API_URL, json=payload)  # Send POST request with JSON body
        response.raise_for_status()  # Raise an exception for bad HTTP status
        data = response.json()

        print("API Response:", json.dumps(data, indent=4))  # Debug: Inspect API response

        if 'data' not in data or f"{symbol}-{fiat}" not in data['data']:
            print(f"Error: '{symbol}-{fiat}' not found in response")
            return None

        return data['data'][f"{symbol}-{fiat}"]
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data for {symbol} in {fiat}: {e}")
        return None

# Load the cache from the JSON file
def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    return {}

# Save the cache to the JSON file
def save_cache(cache):
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=4)

# Function to create the embed with crypto data and optional amount
def create_embed(symbol, fiat, data, amount=1.0):
    price = float(data['last'])  # Get the current price and convert it to float
    percent_change = float(data['priceChangePercentage'])  # Use the correct field for 24h change

    formatted_price = f"{fiat} {price:.2f}"
    total_value = price * amount  # Calculate total value for the given amount
    formatted_total_value = f"{fiat} {total_value:.2f}"
    formatted_percent_change = f"{percent_change:.2f}%"

    updated_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Current local time

    embed = discord.Embed(
        title=f'{symbol} Price in {fiat}',  # Title of the embed
        color=discord.Color.blue()  # Set embed color
    )
    embed.add_field(name='Current Price', value=formatted_price, inline=False)
    embed.add_field(name='24h Change', value=formatted_percent_change, inline=False)
    embed.add_field(name=f'Value of {amount} {symbol}', value=formatted_total_value, inline=False)

    image_path = os.path.join(IMAGES_FOLDER, f"{symbol}.png")
    if os.path.exists(image_path):
        embed.set_thumbnail(url=f"attachment://{symbol}.png")

    embed.set_footer(text=f"Last updated: {updated_time}")

    return embed, image_path

# Command to track a cryptocurrency in a specified fiat currency
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith('!crypto'):
        try:
            parts = message.content.split()
            symbol = parts[1].upper()
            fiat = parts[2].upper()
            channel_id = int(parts[3])
            amount = float(parts[4]) if len(parts) > 4 else 1.0

            data = get_crypto_data(symbol, fiat)
            if data is None:
                await message.channel.send(f"Could not fetch data for {symbol} in {fiat}")
                return

            embed, image_path = create_embed(symbol, fiat, data, amount)

            cache = load_cache()
            # Use unique message ID to track multiple messages in the same or different channels
            message_key = f"{channel_id}-{symbol}-{fiat}-{len(cache)}"
            channel = client.get_channel(channel_id)

            sent_message = await channel.send(embed=embed, files=[discord.File(image_path, filename=f"{symbol}.png")])
            cache[message_key] = {
                'message_id': sent_message.id,
                'symbol': symbol,
                'fiat': fiat,
                'amount': amount,
                'channel_id': channel_id
            }
            save_cache(cache)

            await message.channel.send(f"Tracking {symbol} in {fiat} with amount {amount} in channel {channel_id}")

        except Exception as e:
            await message.channel.send(f"An error occurred: {e}")
            print(f"Error: {e}")

# Function to periodically update crypto data every 5 minutes
@tasks.loop(minutes=5)
async def update_crypto_prices():
    cache = load_cache()
    for message_key, data in cache.items():
        symbol = data['symbol']
        fiat = data['fiat']
        amount = data.get('amount', 1.0)  # Default to 1.0 if not present
        channel_id = data['channel_id']
        channel = client.get_channel(channel_id)
        if not channel:
            continue

        crypto_data = get_crypto_data(symbol, fiat)
        if crypto_data is None:
            continue

        embed, image_path = create_embed(symbol, fiat, crypto_data, amount)

        try:
            cached_message = await channel.fetch_message(data['message_id'])
            await cached_message.edit(embed=embed)
            if os.path.exists(image_path):
                await cached_message.edit(attachments=[discord.File(image_path, filename=f"{symbol}.png")])
        except discord.NotFound:
            print(f"Message {data['message_id']} not found in channel {channel_id}")

# Run the bot
@client.event
async def on_ready():
    print(f'Bot is logged in as {client.user}')
    update_crypto_prices.start()

client.run("YOUR_TOKEN")
