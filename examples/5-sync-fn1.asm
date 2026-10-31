; ==== pages/sync/sync.jsc  atoms=338

; --- fn[1] <null>  args=0 vars=1 closure=3 stack=4 bc=61B insns=32
0000  push_atom_value    atom:75         ; $k75
0005  get_var_ref0                     
0006  typeof                           
0007  eq                               
0008  if_false8          lbl:3           ; -> L000c
000a  get_var_ref0                     
000b  return                           
000c  catch              lbl:26          ; -> L0027
0011  get_var_ref1                     
0012  dup                              
0013  if_true8           lbl:17          ; -> L0025
0015  drop                             
0016  get_var            atom:156        ; Function
001b  dup                              
001c  push_atom_value    atom:357        ; return this
0021  call_constructor   n:1           
0024  call0                            
0025  nip                              
0026  return                           
0027  put_loc0                         
0028  catch              lbl:19          ; -> L0013
002d  push_atom_value    atom:75         ; $k75
0032  get_var_ref2                     
0033  typeof                           
0034  eq                               
0035  if_false8          lbl:4           ; -> L003a
0037  get_var_ref2                     
0038  nip                              
0039  return                           
003a  drop                             
003b  return_undef                     
003c  throw                            
........  ; exact=True len=61
