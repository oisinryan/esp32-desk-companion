#pragma once
#define LGFX_USE_V1
#include <LovyanGFX.hpp>
// Fixed PCB wiring, verified against the running 170x320 radar installation.
class PipDisplay : public lgfx::LGFX_Device {
  lgfx::Panel_ST7789 panel;
  lgfx::Bus_SPI bus;
 public:
  PipDisplay() {
    auto b = bus.config();
    b.spi_host = VSPI_HOST; b.spi_mode = 0;
    b.freq_write = 40000000; b.freq_read = 16000000;
    b.spi_3wire = true; b.use_lock = true; b.dma_channel = SPI_DMA_CH_AUTO;
    b.pin_sclk = 18; b.pin_mosi = 23; b.pin_miso = -1; b.pin_dc = 2;
    bus.config(b); panel.setBus(&bus);
    auto p = panel.config();
    p.pin_cs = 15; p.pin_rst = 4; p.pin_busy = -1;
    p.panel_width = 170; p.panel_height = 320;
    p.memory_width = 240; p.memory_height = 320; p.offset_x = 35;
    p.offset_y = 0; p.offset_rotation = 0;
    p.readable = false; p.invert = true; p.rgb_order = false;
    p.dlen_16bit = false; p.bus_shared = false;
    panel.config(p); setPanel(&panel);
  }
};
