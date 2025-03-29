# Spotify-Palette
A web application that extracts dominant colors from album artwork. This tool allows you to search for albums or view your currently playing track and see the most prominent colors in the album cover. 

# Features
- Search for any album on Spotify.
- View your currently playing track.
- Extracts and displays 5 dominant colors from album artwork including the hex color.
- Limited mode for users without Spotify authentication.

# Setup

1. Install required packages:
   ```
   pip install flask flask-cors requests Pillow colorthief python-dotenv
   ```
2. Create a Spotify Developer app:
- Go to Spotify Developer Dashboard
- Create a new application
- Set the redirect URL to: ``` http://localhost:5000/callback ```
- Note your Client ID and Client Secret

3. Create a ``` credentials.env``` file in the project root with:
   ```
   SPOTIFY_CLIENT_ID = your_client_id_here
   SPOTIFY_CLIENT_SECRET = your_client_secret_here
   REDIRECT_URI = https://localhost:5000/callback

  # Running the Application 

  1. Start the application:
     ``` python spotify_color_extractor.py  ```
  2. Open your browser and navigate to:
     ``` https://localhost:5000 ```
  3. Connect your Spotify account or use limited mode.

This project is licensed under the MIT license. See the LICENSE file for details. 
