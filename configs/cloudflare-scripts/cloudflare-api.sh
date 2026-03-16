#!/bin/bash
set -e

CF_API_TOKEN="${CLOUDFLARE_API_TOKEN:-}"
CF_ZONE_ID="${CLOUDFLARE_ZONE_ID:-}"
CF_ZONE_NAME="${CLOUDFLARE_ZONE_NAME:-}"

# Router IPs
ROUTER_01_IP="172.93.54.112"
ROUTER_02_IP="23.29.118.6"

# App server IPs (for reference)
APP_SERVER_1="100.92.26.38"
APP_SERVER_2="100.89.130.19"

cf_api() {
    local method="$1"
    local endpoint="$2"
    local data="$3"
    
    if [ -z "$CF_API_TOKEN" ]; then
        echo "Error: CLOUDFLARE_API_TOKEN not set" >&2
        return 1
    fi
    
    if [ -z "$CF_ZONE_ID" ]; then
        echo "Error: CLOUDFLARE_ZONE_ID not set" >&2
        return 1
    fi
    
    local url="https://api.cloudflare.com/client/v4$endpoint"
    local args=(-s -X "$method" "$url" \
        -H "Authorization: Bearer $CF_API_TOKEN" \
        -H "Content-Type: application/json")
    
    if [ -n "$data" ]; then
        args+=(-d "$data")
    fi
    
    curl "${args[@]}"
}

# List all zones
list_zones() {
    curl -s -X GET "https://api.cloudflare.com/client/v4/zones" \
        -H "Authorization: Bearer $CF_API_TOKEN" \
        -H "Content-Type: application/json" | jq -r '.result[] | "\(.id) \(.name)"'
}

# Get Zone ID from domain name
get_zone_id() {
    local domain="$1"
    curl -s -X GET "https://api.cloudflare.com/client/v4/zones?name=$domain" \
        -H "Authorization: Bearer $CF_API_TOKEN" \
        -H "Content-Type: application/json" | jq -r '.result[0].id'
}

# Create DNS A record
create_dns_record() {
    local name="$1"
    local content="$2"
    local proxied="${3:-true}"
    local ttl="${4:-1}"
    
    local data=$(cat << JSON
{
    "type": "A",
    "name": "$name",
    "content": "$content",
    "proxied": $proxied,
    "ttl": $ttl
}
JSON
)
    
    cf_api POST "/zones/$CF_ZONE_ID/dns_records" "$data"
}

# Delete DNS record by name
delete_dns_record() {
    local name="$1"
    
    # Find record ID
    local record_id=$(cf_api GET "/zones/$CF_ZONE_ID/dns_records?type=A&name=$name" | jq -r '.result[0].id')
    
    if [ "$record_id" != "null" ] && [ -n "$record_id" ]; then
        cf_api DELETE "/zones/$CF_ZONE_ID/dns_records/$record_id"
        echo "Deleted DNS record: $name"
    else
        echo "DNS record not found: $name"
    fi
}

# Provision staging and production domains
provision_domains() {
    local app_name="$1"
    local base_domain="$2"
    local staging_subdomain="${3:-staging}"
    
    local prod_name="$app_name"
    local staging_name="${staging_subdomain}.${app_name}"
    
    echo "Provisioning domains for $app_name on $base_domain"
    echo "  Production: $prod_name.$base_domain"
    echo "  Staging: $staging_name.$base_domain"
    
    # Production DNS (router-01)
    echo "Creating production DNS record (router-01)..."
    create_dns_record "$prod_name" "$ROUTER_01_IP" true
    
    # Production DNS (router-02)
    echo "Creating production DNS record (router-02)..."
    create_dns_record "$prod_name" "$ROUTER_02_IP" true
    
    # Staging DNS (router-01)
    echo "Creating staging DNS record (router-01)..."
    create_dns_record "$staging_name" "$ROUTER_01_IP" true
    
    # Staging DNS (router-02)
    echo "Creating staging DNS record (router-02)..."
    create_dns_record "$staging_name" "$ROUTER_02_IP" true
    
    echo "DNS records created successfully"
}

# Create password protection for staging
create_staging_password_protection() {
    local zone_id="$1"
    local staging_domain="$2"
    local username="${3:-admin}"
    local password="${4:-}"
    
    if [ -z "$password" ]; then
        password=$(openssl rand -base64 12)
    fi
    
    # Create firewall rule for staging password protection
    local data=$(cat << JSON
{
    "filter": {
        "expression": "(http.host eq \"${staging_domain}\")",
        "paused": false
    },
    "action": "basic_auth",
    "action_parameters": {
        "credentials": [
            {
                "username": "$username",
                "password": "$password"
            }
        ]
    },
    "description": "Password protection for $staging_domain",
    "paused": false
}
JSON
)
    
    cf_api POST "/zones/$zone_id/firewall/access_rules/rules" "$data"
    
    echo "Password protection created for $staging_domain"
    echo "Username: $username"
    echo "Password: $password"
}

# Create security rules
create_security_rules() {
    local zone_id="$1"
    local app_domain="$2"
    
    # Rule 1: Allow legitimate bots
    echo "Creating Rule 1: Allow legitimate bots..."
    local rule1=$(cat << 'JSONRULE'
{
    "filter": {
        "expression": "(cf.client.bot) or (cf.verified_bot_category in {\"Search Engine Crawler\" \"Search Engine Optimization\" \"Monitoring & Analytics\" \"Advertising & Marketing\" \"Page Preview\" \"Academic Research\" \"Security\" \"Accessibility\" \"Webhooks\" \"Feed Fetcher\"}) or (http.user_agent contains \"letsencrypt\" and http.request.uri.path contains \"acme-challenge\")",
        "paused": false
    },
    "action": "allow",
    "description": "Allow legitimate bots and LetsEncrypt",
    "paused": false
}
JSONRULE
)
    cf_api POST "/zones/$zone_id/firewall/rules" "$rule1"
    
    # Rule 2: Block bad bots
    echo "Creating Rule 2: Block bad bots..."
    local rule2=$(cat << 'JSONRULE'
{
    "filter": {
        "expression": "(http.user_agent contains \"yandex\") or (http.user_agent contains \"sogou\") or (http.user_agent contains \"semrush\") or (http.user_agent contains \"aherfs\") or (http.user_agent contains \"baidu\") or (http.user_agent contains \"python-requests\") or (http.user_agent contains \"neevabot\") or (http.user_agent contains \"CF-UC\") or (http.user_agent contains \"sitelock\") or (http.user_agent contains \"crawl\" and not cf.client.bot) or (http.user_agent contains \"bot\" and not cf.client.bot) or (http.user_agent contains \"Bot\" and not cf.client.bot) or (http.user_agent contains \"Crawl\" and not cf.client.bot) or (http.user_agent contains \"spider\" and not cf.client.bot) or (http.user_agent contains \"mj12bot\") or (http.user_agent contains \"ZoominfoBot\") or (http.user_agent contains \"mojeek\") or (ip.src.asnum in {135061 23724 4808} and http.user_agent contains \"siteaudit\")",
        "paused": false
    },
    "action": "block",
    "description": "Block known bad bots",
    "paused": false
}
JSONRULE
)
    cf_api POST "/zones/$zone_id/firewall/rules" "$rule2"
    
    # Rule 3: Block suspicious cloud providers
    echo "Creating Rule 3: Block suspicious cloud providers..."
    local rule3=$(cat << 'JSONRULE'
{
    "filter": {
        "expression": "(ip.src.asnum in {7224 16509 14618 15169 8075 396982} and not cf.client.bot and not cf.verified_bot_category in {\"Search Engine Crawler\" \"Search Engine Optimization\" \"Monitoring & Analytics\" \"Advertising & Marketing\" \"Page Preview\" \"Academic Research\" \"Security\" \"Accessibility\" \"Webhooks\" \"Feed Fetcher\" \"Aggregator\"} and not http.request.uri.path contains \"acme-challenge\")",
        "paused": false
    },
    "action": "challenge",
    "description": "Challenge suspicious cloud provider traffic",
    "paused": false
}
JSONRULE
)
    cf_api POST "/zones/$zone_id/firewall/rules" "$rule3"
    
    # Rule 4: Block WordPress scanners
    echo "Creating Rule 4: Block WordPress scanners..."
    local rule4=$(cat << 'JSONRULE'
{
    "filter": {
        "expression": "(ip.src.asnum in {60068 9009 16247 51332 212238 131199 22298 29761 62639 206150 210277 46562 8100 3214 206092 206074 206164 213074}) or (http.request.uri.path contains \"wp-login\") or (http.request.uri.path contains \"wp-content\") or (http.request.uri.path contains \"wp-includes\") or (http.request.uri.path contains \"wp-admin\") or (http.request.uri.path contains \"php\") or (http.request.uri.path contains \"wp\") or (http.request.uri.path contains \"admin\")",
        "paused": false
    },
    "action": "block",
    "description": "Block WordPress scanners and exploits",
    "paused": false
}
JSONRULE
)
    cf_api POST "/zones/$zone_id/firewall/rules" "$rule4"
    
    # Rule 5: Block malicious actors
    echo "Creating Rule 5: Block malicious actors..."
    local rule5=$(cat << 'JSONRULE'
{
    "filter": {
        "expression": "(ip.src.asnum in {200373 198571 26496 31815 18450 398101 50673 7393 14061 205544 199610 21501 16125 51540 264649 39020 30083 35540 55293 36943 32244 6724 63949 7203 201924 30633 208046 36352 25264 32475 23033 32475 212047 32475 31898 210920 211252 16276 23470 136907 12876 210558 132203 61317 212238 37963 13238 2639 20473 63018 395954 19437 207990 27411 53667 27176 396507 206575 20454 51167 60781 62240 398493 206092 63023 213230 26347 20738 45102 24940 57523 8100 8560 6939 14178 46606 197540 397630 9009 11878}) or (http.request.uri.path contains \"xmlrpc\") or (http.request.uri.path contains \"wp-config\") or (http.request.uri.path contains \"wlwmanifest\") or (cf.verified_bot_category in {\"AI Crawler\" \"Other\"}) or (ip.src.country in {\"T1\"}) or (http.request.uri.path contains \".env\")",
        "paused": false
    },
    "action": "block",
    "description": "Block malicious ASNs and attack patterns",
    "paused": false
}
JSONRULE
)
    cf_api POST "/zones/$zone_id/firewall/rules" "$rule5"
    
    echo "Security rules created successfully"
}

# Main command handler
case "$1" in
    list-zones)
        list_zones
        ;;
    get-zone-id)
        get_zone_id "$2"
        ;;
    create-dns)
        create_dns_record "$2" "$3" "${4:-true}"
        ;;
    delete-dns)
        delete_dns_record "$2"
        ;;
    provision-domains)
        provision_domains "$2" "$3" "$4"
        ;;
    staging-password)
        create_staging_password_protection "$2" "$3" "$4" "$5"
        ;;
    security-rules)
        create_security_rules "$2" "$3"
        ;;
    *)
        echo "Usage: $0 <command> [args]"
        echo ""
        echo "Commands:"
        echo "  list-zones                                   List all zones"
        echo "  get-zone-id <domain>                          Get zone ID for domain"
        echo "  create-dns <name> <ip> [proxied]              Create DNS A record"
        echo "  delete-dns <name>                             Delete DNS record"
        echo "  provision-domains <app> <base> [staging-sub]  Create prod+staging DNS"
        echo "  staging-password <zone_id> <domain> [user] [pass]  Add password protection"
        echo "  security-rules <zone_id> <app_domain>         Create security rules"
        ;;
esac
