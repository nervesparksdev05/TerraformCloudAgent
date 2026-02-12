# MongoDB Atlas Connection Troubleshooting

## Current Issue
Connection to MongoDB Atlas is failing with an authentication error.

## Common Causes & Solutions

### 1. **Network Access / IP Whitelist**
MongoDB Atlas blocks connections by default. You need to whitelist your IP address.

**Fix:**
1. Go to MongoDB Atlas Dashboard: https://cloud.mongodb.com
2. Select your cluster (Cluster0)
3. Click "Network Access" in the left sidebar
4. Click "Add IP Address"
5. Either:
   - Click "Add Current IP Address" (recommended for development)
   - Or click "Allow Access from Anywhere" (0.0.0.0/0) - **ONLY for testing**

### 2. **Database User Credentials**
The username/password in your connection string might be incorrect.

**Current credentials from .env:**
- Username: `shekhar`
- Password: `shekhar123`

**Fix:**
1. Go to MongoDB Atlas Dashboard
2. Click "Database Access" in the left sidebar
3. Verify the user `shekhar` exists
4. If not, create a new user with:
   - Username: `shekhar`
   - Password: `shekhar123`
   - Role: `Atlas admin` or `Read and write to any database`

### 3. **Connection String Format**
Ensure your connection string is properly formatted.

**Current URI:**
```
mongodb+srv://shekhar:shekhar123@cluster0.ez4qzit.mongodb.net/?appName=Cluster0
```

**Correct format should be:**
```
mongodb+srv://shekhar:shekhar123@cluster0.ez4qzit.mongodb.net/terraform_agent?retryWrites=true&w=majority&appName=Cluster0
```

Notice:
- Database name `terraform_agent` should be in the path
- Additional parameters for reliability

## Recommended Steps

1. **First, whitelist your IP** (most common issue)
2. **Then verify database user exists**
3. **Update connection string** in `.env` if needed
4. **Test connection** with `python check_mongo.py`
