// SPDX-License-Identifier: BSD-3-Clause
// A small libretro host used identically by the static and dynamic experiments.
#include "emu.h"
#include "drivenum.h"
#include "mame.h"
#include "libretro.h"
#include "family.h"
#include "infoxml.h"
#include <cstring>
#include <fstream>
#include <vector>
#ifndef RETROM_POC_STATIC
#include <dlfcn.h>
#else
extern "C" retrom_mame_family const *retrom_mame_family_v1();
#endif

namespace {
std::vector<uint32_t> pixels;
std::vector<int16_t> samples;
unsigned width = 0, height = 0, frames = 0;
bool keys[512] = {}, buttons[16] = {};
int16_t axes[2] = {};
retro_system_av_info av_info = {};
bool started = false;
bool shutdown_requested = false;
retro_keyboard_event_t keyboard_event = nullptr;

bool supports_save()
{
    auto *manager = mame_machine_manager::instance();
    return started && manager && manager->machine() &&
        !(manager->machine()->system().type.emulation_flags() & device_t::flags::SAVE_UNSUPPORTED);
}

bool environment(unsigned command, void *data)
{
    switch (command) {
    case RETRO_ENVIRONMENT_SET_KEYBOARD_CALLBACK:
        keyboard_event = static_cast<retro_keyboard_callback *>(data)->callback;
        return true;
    case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
    case RETRO_ENVIRONMENT_GET_CONTENT_DIRECTORY:
    case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY:
        *static_cast<char const **>(data) = "/content";
        return true;
    case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:
        return *static_cast<retro_pixel_format *>(data) == RETRO_PIXEL_FORMAT_XRGB8888;
    case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE:
        *static_cast<bool *>(data) = false;
        return true;
    case RETRO_ENVIRONMENT_GET_VARIABLE: {
        auto *variable = static_cast<retro_variable *>(data);
        variable->value = nullptr;
        // The browser canvas consumes the core's pixels directly. Ask MAME to
        // rotate portrait drivers itself instead of expecting frontend rotation.
        if (std::strstr(variable->key, "_rotation_mode"))
            variable->value = "internal";
        if (std::strstr(variable->key, "_throttle") || std::strstr(variable->key, "_autosave"))
            variable->value = "disabled";
        if (std::strstr(variable->key, "_boot_from_cli"))
            variable->value = "enabled";
        return variable->value != nullptr;
    }
    case RETRO_ENVIRONMENT_SET_SYSTEM_AV_INFO:
        av_info = *static_cast<retro_system_av_info *>(data);
        return true;
    case RETRO_ENVIRONMENT_SET_GEOMETRY:
        av_info.geometry = *static_cast<retro_game_geometry *>(data);
        return true;
    case RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS:
    case RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME:
    case RETRO_ENVIRONMENT_SET_VARIABLES:
        return true;
    case RETRO_ENVIRONMENT_SHUTDOWN:
        shutdown_requested = true;
        return true;
    default:
        return false;
    }
}

void video(void const *data, unsigned w, unsigned h, size_t pitch)
{
    if (!data) return;
    if (!w || !h || w > 4096 || h > 4096) throw std::runtime_error("Invalid frame size");
    width = w;
    height = h;
    pixels.resize(size_t(w) * h);
    for (unsigned row = 0; row < h; ++row)
        std::memcpy(pixels.data() + row * w, static_cast<uint8_t const *>(data) + row * pitch, w * 4);
    ++frames;
}

size_t audio(int16_t const *data, size_t count)
{
    samples.insert(samples.end(), data, data + count * 2);
    return count;
}

void audio_single(int16_t left, int16_t right)
{
    samples.push_back(left);
    samples.push_back(right);
}

int16_t input(unsigned port, unsigned device, unsigned index, unsigned id)
{
    if (port || index) return 0;
    if (device == RETRO_DEVICE_KEYBOARD && id < 512) return keys[id];
    if (device == RETRO_DEVICE_ANALOG && id < 2) return axes[id];
    if (device == RETRO_DEVICE_JOYPAD && id < 16) return buttons[id];
    return 0;
}
}

extern "C" {
int retrom_mame_attach()
{
#ifdef RETROM_POC_STATIC
    auto entry = &retrom_mame_family_v1;
#else
    auto entry = reinterpret_cast<retrom_mame_family const *(*)()>(dlsym(RTLD_DEFAULT, "retrom_mame_family_v1"));
#endif
    if (!entry) return -1;
    auto const *family = entry();
    if (!family || std::strcmp(family->build_id, RETROM_POC_BUILD_ID)) return -2;
    return driver_list::register_family(family->drivers, family->count) ? 0 : -3;
}

unsigned retrom_mame_abi() { return 1; }
char const *retrom_mame_build_id() { return RETROM_POC_BUILD_ID; }
double retrom_mame_fps() { return av_info.timing.fps; }
double retrom_mame_sample_rate() { return av_info.timing.sample_rate; }
double retrom_mame_aspect_ratio() { return av_info.geometry.aspect_ratio; }
void retrom_mame_axis(unsigned id, int value) { if (id < 2 && value >= -32767 && value <= 32767) axes[id] = value; }

unsigned retrom_mame_driver_count() { return driver_list::total(); }
char const *retrom_mame_driver_name(unsigned i) { return i < driver_list::total() ? driver_list::driver(i).name : ""; }

int retrom_mame_listxml()
{
    if (!driver_list::total()) return 0;
    std::ofstream output("/content/mame-arcade.xml", std::ios::binary);
    if (!output) return 0;
    emu_options options;
    info_xml_creator(options, false).output(output, {}, false);
    return output.good() ? 1 : 0;
}

int retrom_mame_start(char const *path)
{
    if (started || !driver_list::total() || !path) return 0;
    retro_set_environment(environment);
    retro_set_video_refresh(video);
    retro_set_audio_sample(audio_single);
    retro_set_audio_sample_batch(audio);
    retro_set_input_poll([] {});
    retro_set_input_state(input);
    retro_init();
    retro_game_info info{path, nullptr, 0, nullptr};
    started = retro_load_game(&info);
    if (started) retro_get_system_av_info(&av_info);
    return started;
}

int retrom_mame_step()
{
    if (!started || shutdown_requested) return 0;
    samples.clear();
    retro_run();
    return !shutdown_requested;
}

void retrom_mame_key(unsigned id, int down)
{
    if (id < 512) {
        keys[id] = down != 0;
        if (keyboard_event) keyboard_event(down != 0, id, id < 128 ? id : 0, 0);
    }
}
void retrom_mame_button(unsigned id, int down) { if (id < 16) buttons[id] = down != 0; }
unsigned retrom_mame_width() { return width; }
unsigned retrom_mame_height() { return height; }
unsigned retrom_mame_frames() { return frames; }
uint32_t const *retrom_mame_pixels() { return pixels.data(); }
int16_t const *retrom_mame_audio() { return samples.data(); }
unsigned retrom_mame_audio_count() { return samples.size(); }
unsigned retrom_mame_save_size() { return supports_save() ? retro_serialize_size() : 0; }
int retrom_mame_save(void *data, unsigned size) { return supports_save() && retro_serialize(data, size); }
int retrom_mame_restore(void const *data, unsigned size) { return supports_save() && retro_unserialize(data, size); }
int retrom_mame_peek(unsigned address)
{
    auto *manager = mame_machine_manager::instance();
    if (!started || !manager || !manager->machine() || address > 65535) return -1;
    auto *cpu = manager->machine()->device<cpu_device>("maincpu");
    return cpu ? cpu->space(AS_PROGRAM).read_byte(address) : -1;
}
void retrom_mame_stop()
{
    if (started) { retro_unload_game(); retro_deinit(); started = false; }
}
}
