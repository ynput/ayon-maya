# AYON Maya USD Chasers

This folder contains AYON Maya USD python import and export chasers to be
registered on Maya startup. These chasers have the ability to influence how
USD data is imported and exported in Maya.

For example, the Filter Properties export chaser allows to filter properties
in the exported USD file to only those that match by the specified pattern
using a SideFX Houdini style pattern matching.

The chasers are registered in the `MayaHost.install` method on Maya launch.

See also the [Maya USD Import Chaser documentation](https://github.com/Autodesk/maya-usd/blob/dev/lib/mayaUsd/commands/Readme.md#import-chasers) 
and [Maya USD Export Chaser documentation](https://github.com/Autodesk/maya-usd/blob/dev/lib/mayaUsd/commands/Readme.md#export-chasers-advanced).