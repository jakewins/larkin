{ pkgs, lib, config, inputs, ... }:

{
  cachix.enable = false;
  
  languages.python = {
    enable = true;
    uv.enable = true;
  };
}