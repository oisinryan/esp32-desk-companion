import test from 'node:test';
import assert from 'node:assert/strict';
import {createNavigator} from '../bridge/navigation.mjs';

function setup(){
 let selected='a',tasks=[{key:'a',updatedAt:1000},{key:'b',updatedAt:1000},{key:'old',updatedAt:0}];
 const opened=[];
 const nav=createNavigator({now:()=>120500,view:()=>({appConnected:true,selectedKey:selected,tasks}),select:key=>{selected=key;},resolveId:key=>key,open:async id=>{opened.push(id);}});
 return {nav,opened,get selected(){return selected;},reverse:()=>{tasks=[...tasks].reverse();}};
}
test('presses cycle only recently active chats in stable order and wrap',async()=>{
 const t=setup();
 await t.nav.handle({id:'12345678-00000001',action:'next'});assert.equal(t.selected,'b');
 t.reverse();
 await t.nav.handle({id:'12345678-00000002',action:'next'});assert.equal(t.selected,'a');
 assert.deepEqual(t.opened,['b','a']);
 await t.nav.handle({id:'12345678-00000003',action:'auto'});assert.equal(t.selected,null);assert.equal(t.opened.length,2);
});
test('concurrent retries of a single button event open exactly one chat',async()=>{
 const t=setup(),event={id:'12345678-00000001',action:'next'};
 const results=await Promise.all([t.nav.handle(event),t.nav.handle(event),t.nav.handle(event)]);
 assert.equal(t.opened.length,1);assert.deepEqual(results[0],results[2]);
});
test('missing active chats and failed app launches are acknowledged without repeated actions',async()=>{
 const empty=createNavigator({view:()=>({appConnected:true,tasks:[]}),select:()=>assert.fail(),resolveId:()=>null});
 assert.equal((await empty.handle({id:'12345678-00000001',action:'next'})).ok,false);
 let calls=0;
 const nav=createNavigator({now:()=>1000,view:()=>({appConnected:true,tasks:[{key:'a',updatedAt:1000}]}),select:()=>{},resolveId:()=> 'a',open:async()=>{calls++;throw Error();}});
 const event={id:'12345678-00000001',action:'next'};
 assert.equal((await nav.handle(event)).ok,false);await nav.handle(event);assert.equal(calls,1);
 await assert.rejects(nav.handle({id:'bad',action:'next'}));
});
