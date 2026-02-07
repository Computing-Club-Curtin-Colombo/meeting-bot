"""Graceful shutdown handling"""
import asyncio
import sys
import signal


def setup_signal_handlers(bot_instance):
    """
    Sets up signal handlers for graceful shutdown.
    
    Args:
        bot_instance: The Discord bot instance to cleanup on shutdown
    """
    def signal_handler(sig, frame):
        """Handle Ctrl+C gracefully"""
        print("\n\nShutting down gracefully...")
        
        # Terminate any active transcription processes
        try:
            from bot.processing.pipeline import terminate_all_processes
            terminate_all_processes()
        except Exception as e:
            print(f"Error terminating processes: {e}")
        
        if bot_instance:
            # Create new event loop for cleanup if needed
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(bot_instance.close())
                else:
                    loop.run_until_complete(bot_instance.close())
            except:
                pass
        sys.exit(0)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
