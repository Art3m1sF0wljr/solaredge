this uses modbus over tcp to request from solaredge se3000h<br>
like instead of doing <br>
echo -ne "\x00\x01\x00\x00\x00\x06\x01\x03\x9C\x52\x00\x02" | nc -w 3 192.168.8.218 1502 | hexdump -C<br>
do this and get the parameters that would be sent over to solaredge server<br>
Also remember to pihole prodssl.solaredge.com<br>
or change the cname, or the dns registry such that it points to nothing<br>
to avoid it calling home<br>
