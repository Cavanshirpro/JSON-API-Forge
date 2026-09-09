function Component()
{
}

Component.prototype.createOperations = function()
{
    component.createOperations();
    if (systemInfo.productType === "windows") {
        component.addOperation(
            "CreateShortcut",
            "@TargetDir@/bin/JSON-API-Forge-Editor.exe",
            "@StartMenuDir@/JSON API Forge Editor.lnk",
            "workingDirectory=@TargetDir@",
            "iconPath=@TargetDir@/bin/JSON-API-Forge-Editor.exe",
            "description=Open JSON API Forge Editor"
        );
        component.addOperation(
            "CreateShortcut",
            "@TargetDir@/bin/JSON-API-Forge-Editor.exe",
            "@DesktopDir@/JSON API Forge Editor.lnk",
            "workingDirectory=@TargetDir@",
            "iconPath=@TargetDir@/bin/JSON-API-Forge-Editor.exe",
            "description=Open JSON API Forge Editor"
        );
    }
}
