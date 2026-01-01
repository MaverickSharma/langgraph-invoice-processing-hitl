"""
Database initialization script
Run this script to create all required database tables
"""
from src.database.db import init_db, reset_db
import sys


def main():
    """Initialize database"""
    print("=" * 60)
    print("LangGraph Invoice Processing - Database Initialization")
    print("=" * 60)
    print()
    
    if len(sys.argv) > 1 and sys.argv[1] == "--reset":
        print("⚠️  RESETTING DATABASE (all data will be lost)...")
        response = input("Are you sure? Type 'yes' to continue: ")
        if response.lower() == 'yes':
            reset_db()
            print("✅ Database reset complete!")
        else:
            print("❌ Database reset cancelled")
            return
    else:
        print("Initializing database tables...")
        init_db()
        print("✅ Database initialized successfully!")
    
    print()
    print("Database location: ./demo.db")
    print()
    print("Tables created:")
    print("  - checkpoints")
    print("  - human_review_queue")
    print("  - workflow_executions")
    print("  - audit_logs")
    print()
    print("You can now start the application with: python app.py")
    print()


if __name__ == "__main__":
    main()
