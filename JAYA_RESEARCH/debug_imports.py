import sys
sys.path.insert(0, 'JAYA_RESEARCH/src')
sys.path.insert(0, 'JAYA_RESEARCH')
print('sys.path prepared')

try:
    import src.teacher as teacher
    print('import src.teacher -> OK')
except Exception as e:
    print('import src.teacher ->', type(e), e)

try:
    import importlib
    importlib.import_module('src.research.academic.reviewer')
    print('import src.research.academic.reviewer -> OK')
except Exception as e:
    import traceback; traceback.print_exc()