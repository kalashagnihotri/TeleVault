import os

path = 'src/face_analysis.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()
    
c = c.replace('if calibration and calibration["reference_set_hash"] == scope_hash:', 
'''if calibration:
                print(f"DEBUG: expected={scope_hash} got={calibration['reference_set_hash']}")
            if calibration and calibration["reference_set_hash"] == scope_hash:''')

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
