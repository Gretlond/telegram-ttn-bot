from docx import Document
import os

def diagnose():
    path = "Шаблоны/Шаблон_ТТН.docx"
    doc = Document(path)
    for table in doc.tables:
        for row in table.rows:
            if any("cargo" in cell.text for cell in row.cells):
                print("🔍 Вот как выглядит XML-код этой строки внутри Word:")
                print(row._tr.xml)
                return
    print("Строка с грузами не найдена.")

if __name__ == "__main__":
    diagnose()