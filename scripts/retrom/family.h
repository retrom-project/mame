// SPDX-License-Identifier: BSD-3-Clause
#pragma once
#include <cstddef>
class game_driver;

struct retrom_mame_family {
    char const *build_id;
    char const *name;
    std::size_t count;
    game_driver const *const *drivers;
};
