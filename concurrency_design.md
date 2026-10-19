# Sprint 2: Server Concurrency Design
## Concurency model

I decided to choose Option B, non-blocking I/O multiplexing, using python selectors moduele.

The server will use a single event loop to manage multiple client connections. Each client socket will be set to non-blocking mode using setblocking(false).

The selectors module will monitor the sockets and notify the server when a client is ready to send or recieve data. This allows the server to communicate with both players without waiting for one player to respond

## Game State Protection
Since I chose selectors, the server uses a single event loop that can handle player moves one at a time. 

this will prevent both players from modifying the game state at the same time. Becuase only one thread updates the game state, threading locks are not needed.

## Turn validation
If the player requests a MOVE message the server will check if it is there turn or not and if its valid.

if the move is invalid an error will be sent without changing anything

if the move was valid the server will update and change the board state

## State Broadcasting 
After a valid move, the server updates the board and then sends a STATE_UPDATE message to both of the players.

the server will use a outgoing buffer for each player and selectors to send the updates when their sockets are ready.

## Score synchronizer
The server keeps player scores in memory.

when the round is ended the server will update the scores sending to both players.