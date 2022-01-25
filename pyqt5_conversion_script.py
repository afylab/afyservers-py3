from glob import glob

# Enter the path to the directory to convert, will convert all files in the directory recusivly (i.e. in all subfolders)
DIRECTORYpath = 'MY DIR'

#----------------------------------------------------------------------------------------------#


QtGUI_to_QtWidget = ["QMainWindow", "QApplication", "QListWidgetItem", "QDialog",
    "QMessageBox", "QSlider", "QInputDialog", "QMenu", "QAction", "QFileDialog",
    "QSpacerItem", "QSizePolicy", "QShortcut", "QPlainTextEdit", "QTextEdit",
    "QWidget", "QVBoxLayout", "QTabWidget", "QLabel", "QComboBox"
    ]

def convert_file(data):
    for i in range(len(data)):
        if "PyQt4" in data[i]:
            data[i] = data[i].replace("PyQt4", "PyQt5")
            print(i, "PyQt4 -> PyQt5")

        if "import" in data[i] and "QtGui" in data[i] and not "QtWidgets" in data[i]:
            data[i] = data[i].replace("QtGui", "QtGui, QtWidgets")
            print(i, "QtGui -> QtGui, QtWidgets")

        for widget in QtGUI_to_QtWidget:
            if "QtGui." + widget in data[i]:
                data[i] = data[i].replace("QtGui." + widget, "QtWidgets." + widget)
                print(i, "QtGui." + widget + "-> QtWidgets." + widget)

    return data
#

files = glob(DIRECTORYpath + '/**/*.py', recursive=True)

for fl in files:
    print("Converting " + fl)
    with open(fl, 'r') as oldfile:
        data = oldfile.readlines()
    data = convert_file(data)
    with open(fl, 'w') as newfile:
        newfile.writelines(data)
    print("")
