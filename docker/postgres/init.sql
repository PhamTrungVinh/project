-- The image runs this script only when initializing an empty data volume.
-- Application tables are created later by each service's migrations.
CREATE DATABASE identity;
CREATE DATABASE ticket;
CREATE DATABASE booking;
CREATE DATABASE event;
CREATE DATABASE chat;
CREATE DATABASE memory;
CREATE DATABASE checkpoints;
