#include "../firmware/include/button.h"
#include <cassert>
#include <cstdio>
int main(){
 BootButton b;
 assert(b.update(true,0)==ButtonAction::None);
 assert(b.update(false,100)==ButtonAction::None);
 assert(b.update(true,110)==ButtonAction::None); // contact bounce
 assert(b.update(false,120)==ButtonAction::None);
 assert(b.update(false,160)==ButtonAction::None);
 assert(b.update(true,220)==ButtonAction::None);
 assert(b.update(true,260)==ButtonAction::Next);
 assert(b.update(true,300)==ButtonAction::None); // one event only
 assert(b.update(false,400)==ButtonAction::None);
 assert(b.update(false,440)==ButtonAction::None);
 assert(b.update(false,1500)==ButtonAction::None); // no autorepeat while held
 assert(b.update(true,1520)==ButtonAction::None);
 assert(b.update(true,1560)==ButtonAction::Auto);
 assert(b.update(true,1600)==ButtonAction::None);
 BootButton wrap;
 wrap.update(false,0xffffff00U);wrap.update(false,0xffffff40U);
 wrap.update(true,0x00000400U);
 assert(wrap.update(true,0x00000440U)==ButtonAction::Auto);
 puts("BOOT debounce, one-shot tap, hold and millis rollover passed");
}
