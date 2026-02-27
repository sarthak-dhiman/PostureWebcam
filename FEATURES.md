# Posture Tracker - Enhanced Features

## Recent Improvements

### 1. Fixed PDF Layout and Timestamp Issues ✅
- **PDF Reports**: Improved chart sizing and positioning for better layout
- **Timestamps**: Fixed timezone conversion - now properly displays local time instead of UTC
- **Dashboard**: Charts now show correct local timestamps

### 2. Configurable Alert Timing ✅
- **Settings Dialog**: Added ⚙️ Settings button in dashboard
- **Alert Timing**: Users can configure after how many seconds to receive alerts (5-300 seconds range)
- **Default**: 30 seconds (as requested)
- **Live Updates**: Configuration reloads automatically every 10 seconds

### 3. Taskbar Widget ✅
- **System Tray Icon**: Shows real-time posture status
- **Status Indicators**:
  - 🟢 Green ✓: Good posture
  - 🔴 Red ✗: Bad posture  
  - ⚪ Gray ?: No body detected
  - ⚪ Gray ○: Tracker not running
- **Context Menu**: Right-click for options
- **Real-time Updates**: Checks status every second

## How to Use

### Running the Application

**Option 1: With Taskbar Widget (Recommended)**
```bash
python run_with_widget.py
```
This starts both the tracker daemon and taskbar widget together.

**Option 2: Traditional Mode**
```bash
python tracker_daemon.py
```
Then separately run:
```bash
python dashboard_app.py
```

**Option 3: Taskbar Widget Only**
```bash
python taskbar_widget.py
```

### Configuring Alerts

1. Open the dashboard (`python dashboard_app.py`)
2. Click the **⚙️ Settings** button
3. Adjust **"Alert after"** to your preferred timing
4. Toggle notifications and sound as needed
5. Click **Save**

Configuration is saved to `data/app_config.json` and takes effect immediately.

### Taskbar Widget Features

- **Status Indicator**: Color-coded icon shows current posture
- **Tooltip**: Hover to see detailed status
- **Right-click Menu**:
  - View current status
  - Open Dashboard
  - Open Settings
  - Quit application

## Configuration Files

- `data/app_config.json`: User settings (alert timing, notifications)
- `data/report_config.json`: Email/report delivery settings

## Technical Details

### Timestamp Fix
- Database stores timestamps in UTC (as before)
- Dashboard and PDF now convert to local timezone for display
- Charts show proper local time on x-axis

### Alert Configuration
- Settings persist in JSON format
- Tracker daemon reloads config every 10 seconds
- No restart required for changes to take effect

### Taskbar Widget
- Uses PyQt6 system tray functionality
- Reads from `live_stats.json` for real-time status
- Minimal resource usage
- Cross-platform compatible (Windows, macOS, Linux)

## Troubleshooting

**Taskbar icon not appearing?**
- Make sure your system supports system tray icons
- Try running as administrator
- Check that PyQt6 is properly installed

**Settings not saving?**
- Ensure `data/` folder exists and is writable
- Check file permissions

**Alerts not working?**
- Verify notifications are enabled in Settings
- Check system notification settings
- Ensure tracker daemon is running
