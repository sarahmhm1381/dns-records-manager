# app.py
from __future__ import annotations
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

from flask import Flask, render_template, request, redirect, url_for, flash
from bson.objectid import ObjectId

# use pymongo only if available / configured
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError, PyMongoError

# ---------- Flask app ----------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "change-me-for-prod")

# ---------- DB configuration (from env) ----------
# Example: MONGO_URI=mongodb://dbuser:secret@host:27017/
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DBNAME = os.environ.get("MONGO_DBNAME", "mydb")

# ---------- DB helper with safe fallback ----------
class SafeDB:
    """Thin wrapper: either real mongo collections or in-memory fallback."""
    def __init__(self, uri: str, dbname: str, timeout_ms: int = 5000):
        self.connected = False
        self._fallback_data = {"dns_server": [], "deleted_history": [], "edited_history": []}
        try:
            self.client = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
            # trigger connection check
            self.client.server_info()
            self.db = self.client[dbname]
            self.dns_server = self.db.get_collection("dns_server")
            self.deleted_history = self.db.get_collection("deleted_history")
            self.edited_history = self.db.get_collection("edited_history")
            self.connected = True
            app.logger.info("Connected to MongoDB at %s", uri)
        except ServerSelectionTimeoutError as e:
            app.logger.warning("MongoDB unavailable (%s). Falling back to in-memory store.", e)
            self.client = None
            self.db = None
            self.dns_server = None
            self.deleted_history = None
            self.edited_history = None
            self.connected = False

    # CRUD helpers (abstract over real collection vs fallback list)
    def insert_dns(self, doc: Dict[str, Any]):
        doc_copy = dict(doc)
        doc_copy["_id"] = str(ObjectId())  # fallback id as string
        if self.connected:
            return self.dns_server.insert_one(doc).inserted_id
        else:
            self._fallback_data["dns_server"].append(doc_copy)
            return doc_copy["_id"]

    def find_all_dns(self) -> List[Dict[str, Any]]:
        if self.connected:
            return list(self.dns_server.find())
        else:
            return list(self._fallback_data["dns_server"])

    def find_one_dns(self, oid: str) -> Optional[Dict[str, Any]]:
        if self.connected:
            return self.dns_server.find_one({"_id": ObjectId(oid)})
        else:
            for d in self._fallback_data["dns_server"]:
                if d.get("_id") == oid:
                    return d
            return None

    def update_dns(self, oid: str, new_fields: Dict[str, Any]):
        if self.connected:
            return self.dns_server.update_one({"_id": ObjectId(oid)}, {"$set": new_fields})
        else:
            for d in self._fallback_data["dns_server"]:
                if d.get("_id") == oid:
                    d.update(new_fields)
                    return True
            return False

    def delete_dns(self, oid: str):
        if self.connected:
            deleted = self.dns_server.find_one_and_delete({"_id": ObjectId(oid)})
            if deleted:
                deleted["deleted_at"] = datetime.now()
                self.deleted_history.insert_one(deleted)
            return deleted
        else:
            for i, d in enumerate(self._fallback_data["dns_server"]):
                if d.get("_id") == oid:
                    deleted = self._fallback_data["dns_server"].pop(i)
                    deleted["deleted_at"] = datetime.now()
                    self._fallback_data["deleted_history"].append(deleted)
                    return deleted
            return None

    def insert_edited_history(self, rec: Dict[str, Any]):
        if self.connected:
            return self.edited_history.insert_one(rec)
        else:
            self._fallback_data["edited_history"].append(rec)
            return True

    # some aggregate helpers used by routes
    def aggregate(self, pipeline):
        if self.connected:
            return list(self.dns_server.aggregate(pipeline))
        else:
            # minimal implementations for endpoints used in this app:
            # - return all dns for simple listing
            if pipeline == []:
                return list(self._fallback_data["dns_server"])
            # for other pipelines, best-effort fallback: return full list
            return list(self._fallback_data["dns_server"])


# instantiate safe db
db_client = SafeDB(MONGO_URI, MONGO_DBNAME)

# ---------- ROUTES ----------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        dns = request.form.get("dns", "").strip()
        ip = request.form.get("ip", "").strip()
        if not dns or not ip:
            flash("Both domain and IP are required.", "warning")
            return redirect(url_for("index"))
        new_doc = {"dns": dns, "ip": ip, "timestamp": datetime.now()}
        db_client.insert_dns(new_doc)
        flash("Submitted.", "success")
        return redirect(url_for("index"))
    all_dns = db_client.find_all_dns()
    return render_template("index.html", dns_server=all_dns)

@app.post("/<id>/delete/")
def delete(id):
    deleted_entry = db_client.delete_dns(id)
    if deleted_entry:
        flash("Deleted.", "info")
    else:
        flash("Entry not found.", "warning")
    return redirect(url_for("index"))

@app.route("/update/<id>", methods=["GET", "POST"])
def update(id):
    old = db_client.find_one_dns(id)
    if not old:
        flash("Entry not found.", "warning")
        return redirect(url_for("index"))
    if request.method == "POST":
        updated_dns = request.form.get("edit-dns", "").strip()
        updated_ip = request.form.get("edit-ip", "").strip()
        if updated_dns and updated_ip:
            db_client.update_dns(id, {"dns": updated_dns, "ip": updated_ip})
            edited_entry = {
                "old_dns": old.get("dns"),
                "old_ip": old.get("ip"),
                "updated_dns": updated_dns,
                "updated_ip": updated_ip,
                "edited_at": datetime.now(),
            }
            db_client.insert_edited_history(edited_entry)
            flash("Updated.", "success")
            return redirect(url_for("index"))
        else:
            flash("Both fields required.", "warning")
    return render_template("edit.html", id=id, old_dns=old.get("dns"), old_ip=old.get("ip"))

@app.route("/search", methods=["GET", "POST"])
def search():
    results = []
    domain = ""
    if request.method == "POST":
        domain = request.form.get("domain", "").strip()
        pipeline = [{"$match": {"dns": {"$regex": "^" + domain, "$options": "i"}}}]
        results = db_client.aggregate(pipeline)
    return render_template("search.html", search_results=results, domain=domain)

@app.route("/searchKeyword", methods=["GET", "POST"])
def search_keyword():
    results = []
    keyword = ""
    if request.method == "POST":
        keyword = request.form.get("keyword", "").strip()
        pipeline = [{"$match": {"$or": [{"dns": {"$regex": keyword, "$options": "i"}},
                                       {"ip": {"$regex": keyword, "$options": "i"}}]}}]
        results = db_client.aggregate(pipeline)
    return render_template("searchK.html", search_results=results, keyword=keyword)

@app.route("/submitted", methods=["GET", "POST"])
def submitted():
    latest_submissions = []
    limit = None
    if request.method == "POST":
        try:
            limit = int(request.form.get("limit", "1"))
        except ValueError:
            limit = 1
        pipeline = [
            {"$sort": {"timestamp": 1}},
            {"$group": {"_id": None, "data": {"$push": "$$ROOT"}}},
            {"$project": {"reversed_data": {"$reverseArray": "$data"}}},
            {"$unwind": "$reversed_data"},
            {"$replaceRoot": {"newRoot": "$reversed_data"}},
            {"$limit": limit},
        ]
        latest_submissions = db_client.aggregate(pipeline)
    return render_template("submitted.html", latest_submissions=latest_submissions, limit=limit)

@app.route("/submission_number")
def submission_number():
    # safe aggregate: if no real aggregation available fallback to length
    if db_client.connected:
        total_pipeline = [{"$count": "total_records"}]
        total_records = list(db_client.dns_server.aggregate(total_pipeline))
        total_count = total_records[0]["total_records"] if total_records else 0
        daily_pipeline = [
            {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                        "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ]
        daily_submissions = list(db_client.dns_server.aggregate(daily_pipeline))
    else:
        total_count = len(db_client.find_all_dns())
        daily_submissions = []
    return render_template("submission_number.html", total_records=total_count, daily_submissions=daily_submissions)

@app.route("/top_level")
def top_level():
    pipeline = [
        {
            "$project": {
                "_id": 0,
                "top_level_domain": {"$arrayElemAt": [{"$split": ["$dns", "."]}, -1]},
                "dns": 1,
                "ip": 1,
            }
        },
        {
            "$group": {
                "_id": "$top_level_domain",
                "dns_records": {"$push": {"dns": "$dns", "ip": "$ip"}}
            }
        },
    ]
    top_level_domains = db_client.aggregate(pipeline)
    return render_template("top_level.html", top_level_domains=top_level_domains)


@app.route("/history")
def history():
    if db_client.connected:
        deleted_pipeline = [{"$sort": {"deleted_at": -1}}, {"$project": {"_id": 0, "dns": 1, "ip": 1, "deleted_at": 1}}]
        deleted_entries = list(db_client.deleted_history.aggregate(deleted_pipeline))
        edited_pipeline = [{"$sort": {"edited_at": -1}}, {"$project": {"_id": 0, "old_dns": 1, "old_ip": 1, "updated_dns": 1, "updated_ip": 1, "edited_at": 1}}]
        edited_entries = list(db_client.edited_history.aggregate(edited_pipeline))
    else:
        deleted_entries = db_client._fallback_data["deleted_history"]
        edited_entries = db_client._fallback_data["edited_history"]
    return render_template("history.html", deleted_entries=deleted_entries, edited_entries=edited_entries)

# ---------- run ----------
if __name__ == "__main__":
    app.run(debug=True)
