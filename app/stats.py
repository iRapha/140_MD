import app.db as db
import app.sentiment as sa

from datetime import datetime, timedelta


def count(tweets):
    if not tweets:
        return {}

    utc_offset = tweets[0]['user']['utc_offset'] / 3600

    counts = dict()
    for tweet in tweets:
        timestamp = datetime.strptime(tweet['created_at'], '%a %b %d %H:%M:%S +0000 %Y')
        minutes = (((timestamp.hour + utc_offset) % 24) * 60 + timestamp.minute)
        if minutes not in counts:
            counts[minutes] = 0
        counts[minutes] += 1
    return counts

def get_poisson_dists(tweets):
    counts = count(tweets)

    probs = dict()
    for timestep in range(0, 24*60, 5):
        probs[timestep] = 0
        for t in counts:
            if timestep - 60 <= t < timestep + 60 or \
               timestep - 60 <= t - 24*60 < timestep + 60 or \
               timestep - 60 <= t + 24*60 < timestep + 60:
                probs[timestep] += counts[t] / 60
    return probs

def get_statistics(tweets):
    probs = get_poisson_dists(tweets)
    sleep_stats = squareFit(probs)
    minutes_awake = get_minutes_sleep(sleep_stats)
    minutes_slept = 24*60 - (minutes_awake)
    db.update_sleep(minutes_slept)
    sent_stats = count_sentiments(tweets)
    hours_slept = "%d:%d" % (minutes_slept // 60, 60*(minutes_slept/60 - (minutes_slept//60)))

    stats = {
        'well_rested': (minutes_slept/ db.get_sleep() > 1),
        'rest_percentage': "%.2f" % abs(100 * minutes_slept/ db.get_sleep() - 100),
        'probs': jsonify_dist(probs),
        'hoursSlept': hours_slept,
        'wakeUpTime': sleep_stats[1],
        'wakeUpTime_str': "%d:%d" % (sleep_stats[1] // 60, 60*(sleep_stats[1]/60 - (sleep_stats[1]//60))),
        'bedTime': sleep_stats[2],
        'bedTime_str': "%d:%d" % (sleep_stats[2] // 60, 60*(sleep_stats[2]/60 - (sleep_stats[2]//60))),
        'sleepCoefficient': "%.2f" % (100 * sleep_stats[0]),
        'sentiment': sent_stats
        }
    return stats


def count_sentiments(tweets, max_num=20):
    sents = { 'positive': 0, 'negative': 0, 'neutral': 0 }

    for tweet in tweets[:max_num]:
        try:
            sents[sa.get_sentiment(tweet['text'])] += 1
        except KeyError:
            continue

    num_tweets = sum(sents.values())
    if num_tweets == 0: num_tweets = 1

    sent_stats = {}
    sent_stats['num_tweets'] = num_tweets
    sent_stats['positive'] = 100 * sents['positive'] / num_tweets
    sent_stats['negative'] = 100 * sents['negative'] / num_tweets

    db_pos = db.get_positive()
    db_neg = db.get_negative()
    db_neu = db.get_neutral()
    db_total = db_pos + db_neg + db_neu

    sent_stats['positive_relative'] = sent_stats['positive'] - (100 * db_pos / db_total)
    sent_stats['negative_relative'] = sent_stats['negative'] - (100 * db_neg / db_total)

    sent_stats['pos_relative_str'] = "%.2f" % (float(sent_stats['positive_relative']))
    sent_stats['neg_relative_str'] = "%.2f" % (float(sent_stats['negative_relative']))

    db.update_sentiment(sents['positive'], sents['negative'], sents['neutral'])
    return sent_stats

def get_minutes_sleep(sleep_stats):
    variance, wake, bed = sleep_stats
    if wake > bed:
        minutes_sleep = bed + (24 * 60 - wake)
    else:
        minutes_sleep = bed - wake
    return minutes_sleep

def squareFit(probs):
    maxVal = max(probs, key=probs.get) #find the max of the set
    mylist = (float('inf'), 0, 0)
    for waketime in range(0, 24 * 60, 10):
        for bedtime in range(0, 24 * 60, 10):
            if (abs(waketime - bedtime) < 60): continue
            variance = varianceCalc(waketime, bedtime, probs, maxVal)
            # print('w ' + str(waketime) + ' b' + str(bedtime) + ' v' + str(variance))
            if (variance < mylist[0]):
                mylist = (variance, waketime, bedtime)
    mylist = (sleepCoefficient(mylist, probs), mylist[1], mylist[2])
    return mylist

def varianceCalc(waketime, bedtime, probs, maxVal):
    variance = 0
    base = 5
    height = averageHeight(probs)
    for position in range(0, 24 * 60, 5):
        if (bedtime > waketime and (waketime < position < bedtime)):
            variance = variance + base * (probs[position] - height)**2
            # print('1' )
        elif ((bedtime < waketime) and (position > bedtime or position < waketime)):
            variance = variance + base * (probs[position] - height)**2
            # print('2' )
        else:
            variance = variance + base * (probs[position])**2
            # print('3' )
    return variance

def sleepCoefficient(mylist, probs):
    maxVariance = sum([5 * (probs[e])**2 for e in probs])
    coefficient = mylist[0] / maxVariance
    return (1 - coefficient)

def averageHeight(probs):
    total = 0
    for i in range(0, 60 * 24, 5):
        total = total + probs[i]
    average = 5 * total / (24 * 60)
    # print("The averaage is " + str(average))
    return average


def jsonify_dist(probs):
    json = []
    for k in probs:
        json.append([k, probs[k]])
    return json
