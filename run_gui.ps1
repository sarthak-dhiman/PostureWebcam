# Launch the mock API (if not already running) and then start the GUI.
# Use the venv python executable for the mock API and pythonw for the GUI.
$pyw = Join-Path $PSScriptRoot "venv310\Scripts\pythonw.exe"
$py = Join-Path $PSScriptRoot "venv310\Scripts\python.exe"
$mock = Join-Path $PSScriptRoot 'mock_api.py'

# Check if mock API is listening on localhost:8000; if not, start it.
$portOpen = $false
try {
	$nc = Test-NetConnection -ComputerName '127.0.0.1' -Port 8000 -WarningAction SilentlyContinue
	if ($nc) { $portOpen = $nc.TcpTestSucceeded }
} catch {
	# ignore failures to run Test-NetConnection on older PS
}

if (-not $portOpen) {
	Write-Host "Starting mock API..."
	Start-Process -FilePath $py -ArgumentList $mock -WindowStyle Minimized
	Start-Sleep -Milliseconds 300
} else {
	Write-Host "Mock API already running on 127.0.0.1:8000"
}

# Launch the GUI using pythonw to avoid a console window
& $pyw (Join-Path $PSScriptRoot 'main.py')
