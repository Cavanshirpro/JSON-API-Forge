cmake_minimum_required(VERSION 3.24)
project(JSONAPIForgeEditor VERSION 0.5.0 LANGUAGES CXX)

set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(FORGE_EDITOR_QT_MIN_VERSION "6.4" CACHE STRING "Minimum supported Qt version")
find_package(Qt6 ${FORGE_EDITOR_QT_MIN_VERSION} REQUIRED COMPONENTS Core Gui Widgets Network)
find_package(Qt6 ${FORGE_EDITOR_QT_MIN_VERSION} QUIET COMPONENTS WebEngineWidgets)
option(FORGE_EDITOR_WARNINGS_AS_ERRORS "Treat editor compiler warnings as errors" OFF)

function(forge_editor_enable_warnings target)
  if(MSVC)
    target_compile_options(${target} PRIVATE /W4 /permissive- /EHsc)
  else()
    target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic -Wconversion -Wshadow)
  endif()
  if(FORGE_EDITOR_WARNINGS_AS_ERRORS)
    if(MSVC)
      target_compile_options(${target} PRIVATE /WX)
    else()
      target_compile_options(${target} PRIVATE -Werror)
    endif()
  endif()
endfunction()

add_library(forge_editor_core STATIC
  src/ApiClient.cpp
  src/ApiClient.hpp
  src/CodeEditor.cpp
  src/CodeEditor.hpp
  src/ConnectionDialog.cpp
  src/ConnectionDialog.hpp
  src/DocumentCodec.cpp
  src/DocumentCodec.hpp
  src/GraphModel.cpp
  src/GraphModel.hpp
  src/JsonHighlighter.cpp
  src/JsonHighlighter.hpp
  src/NodeGraphEditor.cpp
  src/NodeGraphEditor.hpp
  src/PluginManager.cpp
  src/PluginManager.hpp
  src/PluginCatalogClient.cpp
  src/PluginCatalogClient.hpp
  src/PythonSdkPanel.cpp
  src/PythonSdkPanel.hpp
  src/TemplateManager.cpp
  src/TemplateManager.hpp
  src/TeamWorkspace.cpp
  src/TeamWorkspace.hpp
  src/VisualDesigner.cpp
  src/VisualDesigner.hpp
  include/forgeeditor/IEditorPlugin.hpp
)
target_include_directories(forge_editor_core PUBLIC include src)
target_link_libraries(forge_editor_core PUBLIC Qt6::Core Qt6::Gui Qt6::Widgets Qt6::Network)
if(TARGET Qt6::WebEngineWidgets)
  target_link_libraries(forge_editor_core PUBLIC Qt6::WebEngineWidgets)
  target_compile_definitions(forge_editor_core PUBLIC FORGE_EDITOR_HAS_WEBENGINE=1)
endif()
target_compile_definitions(forge_editor_core PUBLIC QT_NO_CAST_FROM_ASCII QT_NO_CAST_TO_ASCII)

forge_editor_enable_warnings(forge_editor_core)

qt_add_executable(JSONAPIForgeEditor
  src/main.cpp
  src/MainWindow.cpp
  src/MainWindow.hpp
  resources/editor.qrc
)
target_link_libraries(JSONAPIForgeEditor PRIVATE forge_editor_core)
forge_editor_enable_warnings(JSONAPIForgeEditor)
if(WIN32)
  target_sources(JSONAPIForgeEditor PRIVATE resources/windows.rc resources/forge-editor.ico)
elseif(APPLE)
  set_source_files_properties(resources/forge-editor.icns PROPERTIES MACOSX_PACKAGE_LOCATION "Resources")
  target_sources(JSONAPIForgeEditor PRIVATE resources/forge-editor.icns)
endif()
set_target_properties(JSONAPIForgeEditor PROPERTIES
  OUTPUT_NAME "JSON-API-Forge-Editor"
  WIN32_EXECUTABLE TRUE
  MACOSX_BUNDLE TRUE
  MACOSX_BUNDLE_BUNDLE_NAME "JSON API Forge Editor"
  MACOSX_BUNDLE_GUI_IDENTIFIER "dev.jsonapiforge.editor"
  MACOSX_BUNDLE_ICON_FILE "forge-editor.icns"
  MACOSX_BUNDLE_SHORT_VERSION_STRING "${PROJECT_VERSION}"
)

install(TARGETS JSONAPIForgeEditor
  BUNDLE DESTINATION .
  RUNTIME DESTINATION bin
)
install(DIRECTORY plugins/ DESTINATION plugins OPTIONAL)
if(UNIX AND NOT APPLE)
  install(FILES resources/dev.jsonapiforge.editor.desktop DESTINATION share/applications)
  install(FILES resources/logo.png
    DESTINATION share/icons/hicolor/512x512/apps
    RENAME dev.jsonapiforge.editor.png
  )
endif()

if(BUILD_TESTING)
  find_package(Qt6 ${FORGE_EDITOR_QT_MIN_VERSION} REQUIRED COMPONENTS Test)
  qt_add_executable(forge_editor_tests tests/tst_editor_core.cpp resources/editor.qrc)
  target_link_libraries(forge_editor_tests PRIVATE forge_editor_core Qt6::Test)
  forge_editor_enable_warnings(forge_editor_tests)
  add_test(NAME forge_editor_core COMMAND forge_editor_tests)
  set_tests_properties(forge_editor_core PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
endif()

set(CPACK_PACKAGE_NAME "JSON-API-Forge-Editor")
set(CPACK_PACKAGE_VENDOR "Cavanshirpro")
set(CPACK_PACKAGE_VERSION "${PROJECT_VERSION}")
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "Policy-aware visual and code editor for JSON API Forge")
set(CPACK_RESOURCE_FILE_LICENSE "${CMAKE_CURRENT_SOURCE_DIR}/../LICENSE")
set(CPACK_GENERATOR "ZIP")
include(CPack)
