// This script runs at container init to create an app user, ensure indexes, and seed system messages.
// Env: MONGO_INITDB_DATABASE is provided by docker-compose as target DB name.
// Use default fallbacks to avoid failures if envs are missing.

const dbName = process.env.MONGO_INITDB_DATABASE || 'streetgpt';
const appUser = process.env.MONGO_USER || 'appuser';
const appPass = process.env.MONGO_PASSWORD || 'apppassword';

print(`Initializing database '${dbName}' and user '${appUser}'...`);

// Switch to target DB
const db = db.getSiblingDB(dbName);

// Create application user with readWrite
try {
  db.createUser({
    user: appUser,
    pwd: appPass,
    roles: [{ role: 'readWrite', db: dbName }]
  });
  print('App user created.');
} catch (e) {
  if (e.codeName === 'DuplicateKey' || /already exists/i.test(e.errmsg || '')) {
    print('App user already exists, continuing.');
  } else {
    throw e;
  }
}

// Ensure indexes for conversations collection
try {
  db.conversations.createIndex({ session_id: 1 }, { unique: true });
  db.conversations.createIndex({ created_at: 1 });
  db.conversations.createIndex({ app: 1 });
  print('Indexes ensured on conversations.');
} catch (e) {
  print('Index creation error: ' + e);
}
