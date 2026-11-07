# endcord-kitty-keyboard
An extension for [endcord](https://github.com/sparklost/endcord) discord TUI client, that adds kitty keyboard protocol support.  
All keybinding codes will remain same, but this will enable terminal-reserved bindings like Ctrl+Z, Ctrl+S, Ctrl+Enter...  
If running in tmux, dont forget to set `allow-passthrough`.  
NOTE: endcord keybinding resolver with `endcord --keybinding` argument, will still use original parser because extensions are not loaded at this point.  
Other kitty extensions: [endcord-image-pfp](https://github.com/sparklost/endcord-image-pfp), [endcord-image-inline](https://github.com/sparklost/endcord-image-inline).  


## Installing
See [official extensions documentation](https://github.com/sparklost/endcord/blob/main/docs/extensions.md#installing-extensions) for installing instructions.
Available options:
- Git clone into `Extensions` directory located in endcord config directory.
- Run `endcord -i https://github.com/sparklost/endcord-kitty-keyboard`
- Or use endcord client-side command `install_extension sparklost/endcord-kitty-keyboard`


## Disclaimer
> [!WARNING]
> Using third-party client is against Discord's Terms of Service and may cause your account to be banned!  
> **Use endcord and/or this extension at your own risk!**  
> If this extension is modified, it may be used for harmful or unintended purposes.  
> **The developer is not responsible for any misuse or for actions taken by users.**  
