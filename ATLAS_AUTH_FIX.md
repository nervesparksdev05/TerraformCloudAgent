# MongoDB Atlas Authentication Fix

## Current Error
`bad auth: authentication failed` - The username/password combination is incorrect.

## Solution Steps

### Option 1: Create New Database User (Recommended)

1. Go to MongoDB Atlas Dashboard: https://cloud.mongodb.com
2. Click **"Database Access"** in the left sidebar
3. Click **"Add New Database User"**
4. Fill in:
   - **Authentication Method**: Password
   - **Username**: `shekhar`
   - **Password**: `shekhar123` (or click "Autogenerate Secure Password")
   - **Database User Privileges**: Select "Built-in Role" → **"Atlas admin"**
5. Click **"Add User"**

### Option 2: Get Connection String from Atlas

1. Go to your cluster (Cluster0)
2. Click **"Connect"**
3. Choose **"Connect your application"**
4. Copy the connection string
5. Replace `<password>` with your actual password
6. Update the `MONGODB_URI` in your `.env` file

### After Creating User

Update your `.env` file with the correct credentials:

```env
MONGODB_URI=mongodb+srv://shekhar:<YOUR_PASSWORD>@cluster0.ez4qzit.mongodb.net/terraform_agent?retryWrites=true&w=majority
```

**Important**: Replace `<YOUR_PASSWORD>` with the actual password you set.

### Test Connection

Run: `python check_mongo.py`

You should see:
```
✅ SUCCESS: Connection established!
```
