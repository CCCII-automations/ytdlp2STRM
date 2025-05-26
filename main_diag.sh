#!/bin/bash

# Diagnostic script to identify duplicate command execution issues
# Run this to check for common causes of duplicate execution

echo "🔍 Diagnosing duplicate command execution..."
echo "=============================================="

# Check if there are multiple instances of the application running
echo "1. Checking for multiple application instances:"
ps aux | grep -E "(python.*main\.py|python.*cli\.py)" | grep -v grep
echo

# Check for multiple socketio handlers
echo "2. Checking for duplicate SocketIO handlers in routes.py:"
grep -n "@socketio.on('execute_command')" */routes.py 2>/dev/null || echo "No routes.py found in current directory"
echo

# Check for multiple Flask apps or SocketIO instances
echo "3. Checking for multiple Flask/SocketIO instances:"
grep -rn "SocketIO(app)" . 2>/dev/null | head -5
echo

# Check for duplicate imports or registrations
echo "4. Checking for duplicate route registrations:"
grep -rn "register.*routes" . 2>/dev/null | head -5
echo

# Check for multiple UI instances
echo "5. Checking for multiple UI instances:"
grep -rn "_ui = Ui()" . 2>/dev/null
echo

# Check recent logs for patterns
echo "6. Checking recent log patterns:"
if [ -f "logs/ytdlp2strm.log" ]; then
    echo "Recent duplicate patterns in logs:"
    tail -20 logs/ytdlp2strm.log | grep -E "(Received command|Modified command)" | head -10
else
    echo "No log file found at logs/ytdlp2strm.log"
fi
echo

# Check for cron or scheduled duplicates
echo "7. Checking cron configuration:"
if [ -f "config/crons.json" ]; then
    echo "Cron configuration:"
    cat config/crons.json | jq . 2>/dev/null || cat config/crons.json
else
    echo "No cron configuration found"
fi
echo

# Check for multiple threads or processes
echo "8. Checking for threading issues:"
grep -rn "Thread.*target.*handle_command" . 2>/dev/null
echo

# Suggestions
echo "🔧 QUICK FIXES:"
echo "=============="
echo "1. Replace ui/ui.py with the fixed version (includes duplicate prevention)"
echo "2. Replace cli.py with the fixed version (fixes import error)"
echo "3. Update routes.py socketio handler (prevents duplicate events)"
echo "4. Restart the application completely (kill all Python processes)"
echo

echo "🚀 VERIFICATION STEPS:"
echo "====================="
echo "1. Kill all existing processes:"
echo "   pkill -f 'python.*main.py'"
echo "   pkill -f 'python.*cli.py'"
echo
echo "2. Start the application:"
echo "   python3 main.py"
echo
echo "3. Test single command from web interface"
echo "4. Check logs for single execution (not duplicate)"
echo

echo "📊 MONITORING:"
echo "============="
echo "   tail -f logs/ytdlp2strm.log | grep -E '(Received command|Would emit|Output:)'"