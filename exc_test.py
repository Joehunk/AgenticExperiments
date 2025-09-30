import traceback

def kaboom():
    raise ValueError("Kaboom!")

def catch_kaboom():
    try:
        kaboom()
    except Exception as e:
        return traceback.format_tb(e.__traceback__)
    
print(catch_kaboom())