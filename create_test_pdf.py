#!/usr/bin/env python3
"""
Quick script to create a simple test PDF menu
"""
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

def create_test_menu_pdf(filename="test_menu.pdf"):
    c = canvas.Canvas(filename, pagesize=letter)
    width, height = letter
    
    y = height - inch
    
    # Title
    c.setFont("Helvetica-Bold", 20)
    c.drawString(inch, y, "TEST RESTAURANT MENU")
    y -= 0.5 * inch
    
    # Appetizers
    c.setFont("Helvetica-Bold", 14)
    c.drawString(inch, y, "APPETIZERS")
    y -= 0.3 * inch
    
    c.setFont("Helvetica", 11)
    c.drawString(inch, y, "Bruschetta - $8.99")
    y -= 0.2 * inch
    c.setFont("Helvetica", 9)
    c.drawString(inch + 0.2*inch, y, "Fresh tomatoes, basil, and mozzarella on toasted bread")
    y -= 0.3 * inch
    
    c.setFont("Helvetica", 11)
    c.drawString(inch, y, "Mozzarella Sticks - $7.50")
    y -= 0.2 * inch
    c.setFont("Helvetica", 9)
    c.drawString(inch + 0.2*inch, y, "Crispy fried mozzarella served with marinara sauce")
    y -= 0.5 * inch
    
    # Main Dishes
    c.setFont("Helvetica-Bold", 14)
    c.drawString(inch, y, "MAIN DISHES")
    y -= 0.3 * inch
    
    c.setFont("Helvetica", 11)
    c.drawString(inch, y, "Fettuccine Alfredo - $15.99")
    y -= 0.2 * inch
    c.setFont("Helvetica", 9)
    c.drawString(inch + 0.2*inch, y, "Creamy parmesan sauce with fresh fettuccine pasta")
    y -= 0.3 * inch
    
    c.setFont("Helvetica", 11)
    c.drawString(inch, y, "Margherita Pizza - $12.99")
    y -= 0.2 * inch
    c.setFont("Helvetica", 9)
    c.drawString(inch + 0.2*inch, y, "Fresh mozzarella, tomatoes, basil on wood-fired crust")
    y -= 0.3 * inch
    
    c.setFont("Helvetica", 11)
    c.drawString(inch, y, "Grilled Salmon - $18.99")
    y -= 0.2 * inch
    c.setFont("Helvetica", 9)
    c.drawString(inch + 0.2*inch, y, "Atlantic salmon with lemon butter sauce, served with vegetables")
    y -= 0.5 * inch
    
    # Desserts
    c.setFont("Helvetica-Bold", 14)
    c.drawString(inch, y, "DESSERTS")
    y -= 0.3 * inch
    
    c.setFont("Helvetica", 11)
    c.drawString(inch, y, "Tiramisu - $6.99")
    y -= 0.2 * inch
    c.setFont("Helvetica", 9)
    c.drawString(inch + 0.2*inch, y, "Classic Italian dessert with espresso and mascarpone")
    y -= 0.3 * inch
    
    c.setFont("Helvetica", 11)
    c.drawString(inch, y, "Chocolate Lava Cake - $7.50")
    y -= 0.2 * inch
    c.setFont("Helvetica", 9)
    c.drawString(inch + 0.2*inch, y, "Warm chocolate cake with vanilla ice cream")
    
    c.save()
    print(f"✅ Created {filename}")

if __name__ == "__main__":
    try:
        create_test_menu_pdf()
    except ImportError:
        print("❌ reportlab not installed. Installing...")
        import subprocess
        subprocess.run(["pip", "install", "reportlab"], check=True)
        create_test_menu_pdf()
